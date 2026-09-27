import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from email.message import Message
from pathlib import Path

from tools.bulk_resolve import (
    JsonHttpClient,
    _argument_parser,
    build_overpass_query,
    build_wikidata_request,
    derive_focal_candidates,
    overpass_to_geojson,
    resolve_record,
    run_pipeline,
    score_wikidata_candidate,
    select_wikidata_candidate,
)


VENUE = {
    "venue_id": "wembley-stadium-london-england-stadium",
    "canonical_name": "Wembley Stadium",
    "city": "London",
    "country": "England",
    "venue_class": "stadium",
    "source_line": 17,
}
STRICT_VENUE = {
    **VENUE,
    "identity_discriminators": ["association football"],
}


class HttpClientTests(unittest.TestCase):
    def test_429_is_retried_and_successful_json_is_returned(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(429),
            {"search": [{"id": "Q1"}]},
        ])
        client = JsonHttpClient(
            timeout=12,
            max_retries=2,
            backoff_base=0.5,
            request_interval=0,
            opener=opener,
            sleep=time.sleep,
            monotonic=time.monotonic,
            wall_time=time.time,
        )

        result = client.fetch(build_wikidata_request(VENUE))

        self.assertEqual(result, {"search": [{"id": "Q1"}]})
        self.assertEqual(opener.timeouts, [12, 12])
        self.assertEqual(time.sleeps, [0.5])

    def test_retry_after_header_sets_minimum_retry_delay(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(429, retry_after="7"),
            {"search": []},
        ])
        client = JsonHttpClient(
            max_retries=1,
            backoff_base=0.5,
            request_interval=0,
            opener=opener,
            sleep=time.sleep,
            monotonic=time.monotonic,
            wall_time=time.time,
        )

        self.assertEqual(client.fetch(build_wikidata_request(VENUE)), {"search": []})
        self.assertEqual(time.sleeps, [7.0])

    def test_future_retry_after_http_date_sets_minimum_retry_delay(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(
                429, retry_after="Tue, 14 Nov 2023 22:13:30 GMT"
            ),
            {"search": []},
        ])
        client = _test_client(opener, time)

        self.assertEqual(client.fetch(build_wikidata_request(VENUE)), {"search": []})
        self.assertEqual(time.sleeps, [10.0])

    def test_past_retry_after_http_date_falls_back_to_exponential_delay(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(
                429, retry_after="Tue, 14 Nov 2023 22:13:10 GMT"
            ),
            {"search": []},
        ])
        client = _test_client(opener, time)

        self.assertEqual(client.fetch(build_wikidata_request(VENUE)), {"search": []})
        self.assertEqual(time.sleeps, [1])

    def test_malformed_retry_after_falls_back_to_exponential_delay(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(429, retry_after="eventually"),
            {"search": []},
        ])
        client = _test_client(opener, time)

        self.assertEqual(client.fetch(build_wikidata_request(VENUE)), {"search": []})
        self.assertEqual(time.sleeps, [1])

    def test_5xx_is_retried_and_successful_json_is_returned(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(502),
            {"elements": []},
        ])
        client = _test_client(opener, time, backoff_base=0.25)

        self.assertEqual(client.fetch(build_wikidata_request(VENUE)), {"elements": []})
        self.assertEqual(time.sleeps, [0.25])

    def test_retryable_failure_is_raised_after_max_retries(self):
        time = _FakeTime()
        opener = _SequenceOpener([
            _http_error(503), _http_error(503), _http_error(503),
        ])
        client = JsonHttpClient(
            max_retries=2,
            backoff_base=1,
            request_interval=0,
            opener=opener,
            sleep=time.sleep,
            monotonic=time.monotonic,
            wall_time=time.time,
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            client.fetch(build_wikidata_request(VENUE))

        self.assertEqual(raised.exception.code, 503)
        self.assertEqual(opener.calls, 3)
        self.assertEqual(time.sleeps, [1, 2])

    def test_permanent_400_is_not_retried(self):
        time = _FakeTime()
        opener = _SequenceOpener([_http_error(400)])
        client = JsonHttpClient(
            max_retries=4,
            request_interval=0,
            opener=opener,
            sleep=time.sleep,
            monotonic=time.monotonic,
            wall_time=time.time,
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            client.fetch(build_wikidata_request(VENUE))

        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(opener.calls, 1)
        self.assertEqual(time.sleeps, [])

    def test_requests_are_paced_by_start_time(self):
        time = _FakeTime()
        opener = _SequenceOpener([{"search": []}, {"search": []}])
        client = JsonHttpClient(
            request_interval=2,
            opener=opener,
            sleep=time.sleep,
            monotonic=time.monotonic,
            wall_time=time.time,
        )

        client.fetch(build_wikidata_request(VENUE))
        client.fetch(build_wikidata_request(VENUE))

        self.assertEqual(time.sleeps, [2])

    def test_cli_exposes_timeout_retry_backoff_and_pacing_controls(self):
        arguments = _argument_parser().parse_args([
            "venues.json", "resolved.json", "--cache-dir", "cache",
            "--request-timeout", "45", "--max-retries", "7",
            "--backoff-base", "1.5", "--request-interval", "2.5",
        ])

        self.assertEqual(arguments.request_timeout, 45)
        self.assertEqual(arguments.max_retries, 7)
        self.assertEqual(arguments.backoff_base, 1.5)
        self.assertEqual(arguments.request_interval, 2.5)

    def test_cli_uses_conservative_request_defaults(self):
        arguments = _argument_parser().parse_args([
            "venues.json", "resolved.json", "--cache-dir", "cache",
        ])

        self.assertEqual(arguments.request_timeout, 90)
        self.assertEqual(arguments.max_retries, 5)
        self.assertEqual(arguments.backoff_base, 2)
        self.assertEqual(arguments.request_interval, 1)

    def test_cli_rejects_non_finite_or_non_positive_timeout(self):
        for value in ("0", "-1", "nan", "inf", "-inf"):
            with self.subTest(value=value):
                self._assert_cli_error("--request-timeout", value)

    def test_cli_rejects_negative_retry_count(self):
        self._assert_cli_error("--max-retries", "-1")

    def test_cli_rejects_non_finite_or_negative_delay_controls(self):
        for option in ("--backoff-base", "--request-interval"):
            for value in ("-1", "nan", "inf", "-inf"):
                with self.subTest(option=option, value=value):
                    self._assert_cli_error(option, value)

    def _assert_cli_error(self, option, value):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                _argument_parser().parse_args([
                    "venues.json", "resolved.json", "--cache-dir", "cache",
                    option, value,
                ])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("error:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class WikidataResolutionTests(unittest.TestCase):
    def test_search_request_uses_canonical_name_only_and_api_limits(self):
        request = build_wikidata_request(VENUE)
        parsed = urllib.parse.urlparse(request.full_url)
        parameters = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "www.wikidata.org")
        self.assertEqual(parameters["action"], ["wbsearchentities"])
        self.assertEqual(parameters["search"], ["Wembley Stadium"])
        self.assertEqual(parameters["language"], ["en"])
        self.assertEqual(parameters["type"], ["item"])
        self.assertEqual(parameters["limit"], ["10"])
        self.assertIn("stadia-coordinate-resolver", request.get_header("User-agent"))

    def test_candidate_requires_exact_label_or_alias_and_both_locations(self):
        alias_match = {
            "id": "Q1",
            "label": "Wembley",
            "aliases": ["Wembley Stadium"],
            "description": "association football stadium in London, England",
        }
        wrong_city = dict(alias_match, description="stadium in Bristol, England")
        partial_name = dict(alias_match, aliases=[], label="Wembley Park")
        york_venue = {
            **STRICT_VENUE,
            "canonical_name": "York Stadium",
            "city": "York",
            "country": "United States",
        }
        new_york_candidate = {
            "id": "Q2",
            "label": "York Stadium",
            "description": "association football stadium in New York, United States",
        }

        self.assertGreater(score_wikidata_candidate(STRICT_VENUE, alias_match), 0)
        self.assertIsNone(score_wikidata_candidate(STRICT_VENUE, wrong_city))
        self.assertIsNone(score_wikidata_candidate(STRICT_VENUE, partial_name))
        self.assertIsNone(score_wikidata_candidate(york_venue, new_york_candidate))

    def test_generic_unique_candidate_without_source_discriminator_is_unresolved(self):
        candidate = {
            "id": "Q1",
            "label": "Wembley Stadium",
            "description": "association football stadium in London, England",
            "match": {"type": "label"},
            "quality": "high",
        }

        response = {"search": [candidate]}
        self.assertIsNone(score_wikidata_candidate(VENUE, candidate))
        self.assertIsNone(select_wikidata_candidate(VENUE, response))
        self.assertEqual(
            resolve_record(VENUE, response, None)["resolution_reason"],
            "wikidata_identity_unresolved",
        )

    def test_record_discriminator_allows_one_matching_candidate(self):
        candidate = {
            "id": "Q1",
            "label": "Wembley Stadium",
            "description": "association football stadium in London, England",
        }

        self.assertGreater(score_wikidata_candidate(STRICT_VENUE, candidate), 0)
        self.assertEqual(
            select_wikidata_candidate(STRICT_VENUE, {"search": [candidate]})["id"],
            "Q1",
        )

    def test_selector_rejects_ambiguous_top_scoring_identities(self):
        exact_label = {
            "id": "Q1", "label": "Wembley Stadium",
            "description": "association football stadium in London, England",
        }
        alias_match = {
            "id": "Q2", "label": "Wembley",
            "aliases": ["Wembley Stadium"],
            "description": "association football stadium in London, England",
        }
        result = select_wikidata_candidate(
            STRICT_VENUE, {"search": [exact_label, alias_match]}
        )

        self.assertGreater(score_wikidata_candidate(STRICT_VENUE, exact_label), 0)
        self.assertGreater(score_wikidata_candidate(STRICT_VENUE, alias_match), 0)
        self.assertIsNone(result)

    def test_current_candidate_is_selected_over_clearly_disused_candidate(self):
        current = {
            "id": "Q1", "label": "Wembley Stadium",
            "description": "association football stadium in London, England",
        }
        disused = {
            "id": "Q2", "label": "Wembley Stadium",
            "description": "former association football stadium in London, England",
        }

        result = select_wikidata_candidate(
            STRICT_VENUE, {"search": [disused, current]}
        )

        self.assertEqual(result["id"], "Q1")
        self.assertIsNone(score_wikidata_candidate(STRICT_VENUE, disused))

    def test_selector_uses_a_unique_location_matched_identity(self):
        result = select_wikidata_candidate(STRICT_VENUE, {"search": [
            {
                "id": "Q1", "label": "Wembley Stadium",
                "description": "association football stadium in London, England",
            },
            {
                "id": "Q2", "label": "Wembley Stadium",
                "description": "railway station in London, England",
            },
        ]})

        self.assertEqual(result["id"], "Q1")


class OsmResolutionTests(unittest.TestCase):
    def test_overpass_query_is_anchored_by_qid_and_class_rules(self):
        stadium = build_overpass_query("Q123", "stadium")
        circuit = build_overpass_query("Q123", "circuit")

        self.assertIn('nwr["wikidata"="Q123"]', stadium)
        self.assertIn('["leisure"="pitch"]', stadium)
        self.assertIn("map_to_area", stadium)
        self.assertIn("(area.venueArea)", stadium)
        self.assertIn('nwr["wikidata"="Q123"]', circuit)
        self.assertIn('["highway"="raceway"]', circuit)
        self.assertIn('["raceway"="start_finish"]', circuit)
        self.assertNotIn('motor_racing"="starting_grid', circuit)
        self.assertIn("around.mainTrack:10", circuit)
        self.assertIn("out meta geom", circuit)
        self.assertNotIn("out tags meta", circuit)
        self.assertNotIn("center", stadium)

    def test_overpass_query_rejects_injected_qids_and_unknown_classes(self):
        with self.assertRaises(ValueError):
            build_overpass_query('Q1"];out;', "stadium")
        with self.assertRaises(ValueError):
            build_overpass_query("Q1", "velodrome")

    def test_overpass_conversion_uses_geometry_but_never_server_centres(self):
        converted = overpass_to_geojson({"elements": [
            {
                "type": "way", "id": 10,
                "version": 7,
                "timestamp": "2026-09-12T10:30:00Z",
                "changeset": 12345,
                "tags": {"leisure": "pitch", "sport": "soccer"},
                "geometry": [
                    {"lat": 51.0, "lon": -0.2},
                    {"lat": 51.0, "lon": -0.1},
                    {"lat": 51.1, "lon": -0.1},
                    {"lat": 51.1, "lon": -0.2},
                    {"lat": 51.0, "lon": -0.2},
                ],
            },
            {
                "type": "relation", "id": 11,
                "tags": {"leisure": "pitch"},
                "center": {"lat": 51.05, "lon": -0.15},
            },
        ]})

        self.assertEqual(len(converted["features"]), 1)
        self.assertEqual(converted["features"][0]["geometry"]["type"], "Polygon")
        self.assertEqual(converted["features"][0]["properties"]["osm_id"], "way/10")
        self.assertEqual(converted["features"][0]["properties"]["osm_version"], 7)
        self.assertEqual(
            converted["features"][0]["properties"]["osm_timestamp"],
            "2026-09-12T10:30:00Z",
        )

    def test_closed_raceway_is_preserved_as_a_centreline_not_a_polygon(self):
        converted = overpass_to_geojson({"elements": [{
            "type": "way", "id": 10,
            "tags": {"highway": "raceway"},
            "geometry": [
                {"lat": 51.0, "lon": -0.2},
                {"lat": 51.0, "lon": -0.1},
                {"lat": 51.1, "lon": -0.1},
                {"lat": 51.1, "lon": -0.2},
                {"lat": 51.0, "lon": -0.2},
            ],
        }]})

        self.assertEqual(
            converted["features"][0]["geometry"]["type"], "LineString"
        )

    def test_stadium_requires_pitch_polygon_not_venue_or_building_polygon(self):
        geojson = {"type": "FeatureCollection", "features": [
            _polygon_feature("way/1", {"leisure": "stadium"}),
            _polygon_feature("way/2", {"building": "stadium"}),
            _polygon_feature("way/3", {"leisure": "pitch", "sport": "soccer"}),
        ]}

        candidates = derive_focal_candidates("stadium", geojson)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["osm_focal_id"], "way/3")
        self.assertAlmostEqual(candidates[0]["candidate_lat"], 51.05)
        self.assertAlmostEqual(candidates[0]["candidate_lon"], -0.15)

    def test_geojson_element_version_is_preserved_in_focal_provenance(self):
        feature = _polygon_feature(
            "way/3", {"leisure": "pitch", "sport": "soccer"}
        )
        feature["properties"] = {
            "@id": "way/3",
            "@version": 9,
            "tags": {"leisure": "pitch", "sport": "soccer"},
        }

        candidate = derive_focal_candidates("stadium", {
            "type": "FeatureCollection", "features": [feature]
        })[0]

        self.assertEqual(candidate["osm_focal_version"], 9)

    def test_arena_pitch_must_be_explicitly_indoor(self):
        geojson = {"type": "FeatureCollection", "features": [
            _polygon_feature("way/1", {"leisure": "pitch", "sport": "basketball"}),
            _polygon_feature(
                "way/2", {"leisure": "pitch", "sport": "basketball", "indoor": "yes"}
            ),
        ]}

        self.assertEqual(
            [row["osm_focal_id"] for row in derive_focal_candidates("arena", geojson)],
            ["way/2"],
        )

    def test_golf_requires_an_explicit_18th_green(self):
        geojson = {"type": "FeatureCollection", "features": [
            _polygon_feature("way/1", {"golf": "green", "ref": "17"}),
            _polygon_feature("way/2", {"golf": "green", "ref": "18"}),
        ]}

        self.assertEqual(
            [row["osm_focal_id"] for row in derive_focal_candidates("golf", geojson)],
            ["way/2"],
        )

    def test_circuit_requires_explicit_start_finish_not_raceway_midpoint(self):
        geojson = {"type": "FeatureCollection", "features": [
            _line_feature("way/1", {"highway": "raceway"}, [
                [-0.2, 51.05], [-0.1, 51.05],
            ]),
            _point_feature("node/2", {"raceway": "start_finish"}),
            _point_feature("node/3", {"motor_racing": "starting_grid"}),
        ]}

        candidates = derive_focal_candidates("circuit", geojson)

        self.assertEqual([row["osm_focal_id"] for row in candidates], ["node/2"])
        self.assertEqual(candidates[0]["candidate_lat"], 51.05)
        self.assertEqual(candidates[0]["candidate_lon"], -0.15)
        self.assertEqual(candidates[0]["osm_track_id"], "way/1")
        self.assertLessEqual(candidates[0]["track_distance_m"], 10)

    def test_circuit_rejects_start_finish_without_main_track_or_beyond_10m(self):
        marker = _point_feature_at(
            "node/2", {"raceway": "start_finish"}, -0.15, 51.0502
        )

        self.assertEqual(derive_focal_candidates(
            "circuit", {"type": "FeatureCollection", "features": [marker]}
        ), [])
        self.assertEqual(derive_focal_candidates("circuit", {
            "type": "FeatureCollection",
            "features": [
                _line_feature("way/1", {"highway": "raceway"}, [
                    [-0.2, 51.05], [-0.1, 51.05],
                ]),
                marker,
            ],
        }), [])

    def test_racecourse_requires_explicit_winning_post_or_finish(self):
        geojson = {"type": "FeatureCollection", "features": [
            _line_feature(
                "way/1", {"leisure": "track", "sport": "horse_racing"},
                [[-0.2, 51.05], [-0.1, 51.05]],
            ),
            _point_feature_at(
                "node/2", {"horse_racing": "winning_post"}, -0.15, 51.0501
            ),
        ]}

        candidates = derive_focal_candidates("racecourse", geojson)

        self.assertEqual([row["osm_focal_id"] for row in candidates], ["node/2"])
        self.assertEqual(candidates[0]["osm_track_id"], "way/1")
        self.assertLessEqual(candidates[0]["track_distance_m"], 15)

    def test_racecourse_rejects_winning_post_beyond_15m(self):
        geojson = {"type": "FeatureCollection", "features": [
            _line_feature(
                "way/1", {"leisure": "track", "sport": "horse_racing"},
                [[-0.2, 51.05], [-0.1, 51.05]],
            ),
            _point_feature_at(
                "node/2", {"horse_racing": "winning_post"}, -0.15, 51.0502
            ),
        ]}

        self.assertEqual(derive_focal_candidates("racecourse", geojson), [])


class RecordAndPipelineTests(unittest.TestCase):
    def test_resolver_emits_manual_state_without_any_coordinate_fallback(self):
        result = resolve_record(VENUE, {"search": []}, None)

        self.assertEqual(result["status"], "manual_required")
        self.assertEqual(result["resolution_reason"], "wikidata_identity_unresolved")
        self.assertNotIn("candidate_lat", result)
        self.assertNotIn("candidate_lon", result)
        self.assertNotIn("final_lat", result)
        self.assertNotIn("final_lon", result)

    def test_resolver_only_auto_selects_one_focal_geometry(self):
        wikidata = {"search": [{
            "id": "Q1", "label": "Wembley Stadium",
            "description": "association football stadium in London, England",
        }]}
        one_pitch = {"type": "FeatureCollection", "features": [
            _polygon_feature("way/2", {"leisure": "stadium", "wikidata": "Q1"}),
            _polygon_feature("way/3", {"leisure": "pitch", "sport": "soccer"}),
        ]}
        two_pitches = {"type": "FeatureCollection", "features": [
            *one_pitch["features"],
            _polygon_feature("way/4", {"leisure": "pitch", "sport": "soccer"}),
        ]}

        resolved = resolve_record(STRICT_VENUE, wikidata, one_pitch)
        ambiguous = resolve_record(STRICT_VENUE, wikidata, two_pitches)
        unanchored = resolve_record(STRICT_VENUE, wikidata, {
            "type": "FeatureCollection",
            "features": [one_pitch["features"][1]],
        })

        self.assertEqual(resolved["status"], "auto_candidate")
        self.assertEqual(resolved["qid"], "Q1")
        self.assertEqual(resolved["osm_site_id"], "way/2")
        self.assertEqual(resolved["osm_focal_id"], "way/3")
        self.assertEqual(ambiguous["status"], "manual_required")
        self.assertEqual(ambiguous["resolution_reason"], "focal_geometry_ambiguous")
        self.assertNotIn("candidate_lat", ambiguous)
        self.assertEqual(unanchored["status"], "manual_required")
        self.assertEqual(unanchored["resolution_reason"], "osm_identity_unresolved")
        self.assertNotIn("candidate_lat", unanchored)

    def test_offline_pipeline_is_resumable_and_uses_cached_source_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "venues.json"
            output = root / "resolved.json"
            cache = root / "cache"
            (cache / "wikidata").mkdir(parents=True)
            (cache / "overpass").mkdir()
            source.write_text(json.dumps([STRICT_VENUE]), encoding="utf-8")
            wikidata_request = build_wikidata_request(STRICT_VENUE)
            wikidata_hash = hashlib.sha256(
                wikidata_request.full_url.encode("utf-8")
            ).hexdigest()
            wikidata_cache = (
                cache / "wikidata"
                / f'{VENUE["venue_id"]}-v2-name-only-{wikidata_hash}.json'
            )
            wikidata_cache.write_text(
                json.dumps({
                    "batchcomplete": "",
                    "search": [{
                        "id": "Q1", "label": "Wembley Stadium",
                        "description": "association football stadium in London, England",
                    }],
                }), encoding="utf-8"
            )
            query = build_overpass_query("Q1", "stadium")
            query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
            overpass_cache = cache / "overpass" / f"Q1-stadium-{query_hash}.json"
            overpass_cache.write_text(json.dumps({
                "version": 0.6,
                "generator": "Overpass API 0.7.62",
                "osm3s": {"timestamp_osm_base": "2026-09-13T00:00:00Z"},
                "elements": [
                    {
                        "type": "way", "id": 2,
                        "version": 4,
                        "timestamp": "2026-09-11T10:00:00Z",
                        "tags": {"leisure": "stadium", "wikidata": "Q1"},
                        "geometry": [
                            {"lat": 50.9, "lon": -0.3},
                            {"lat": 50.9, "lon": 0.0},
                            {"lat": 51.2, "lon": 0.0},
                            {"lat": 51.2, "lon": -0.3},
                            {"lat": 50.9, "lon": -0.3},
                        ],
                    },
                    {
                        "type": "way", "id": 3,
                        "version": 8,
                        "timestamp": "2026-09-12T10:00:00Z",
                        "tags": {"leisure": "pitch", "sport": "soccer"},
                        "geometry": [
                            {"lat": 51.0, "lon": -0.2},
                            {"lat": 51.0, "lon": -0.1},
                            {"lat": 51.1, "lon": -0.1},
                            {"lat": 51.1, "lon": -0.2},
                            {"lat": 51.0, "lon": -0.2},
                        ],
                    },
                ],
            }), encoding="utf-8")

            run_pipeline(source, output, cache, offline=True)
            first = json.loads(output.read_text(encoding="utf-8"))
            source.write_text("[]", encoding="utf-8")
            run_pipeline(source, output, cache, offline=True, resume=True)

            self.assertEqual(first[0]["status"], "auto_candidate")
            self.assertEqual(first[0]["osm_site_version"], 4)
            self.assertEqual(first[0]["osm_focal_version"], 8)
            self.assertEqual(
                first[0]["source_snapshots"]["wikidata"]["cache_key"],
                f'wikidata/{wikidata_cache.name}',
            )
            self.assertEqual(
                first[0]["source_snapshots"]["wikidata"]["request"][
                    "query_sha256"
                ],
                wikidata_hash,
            )
            self.assertEqual(
                first[0]["source_snapshots"]["osm"]["osm_base_timestamp"],
                "2026-09-13T00:00:00Z",
            )
            self.assertEqual(
                first[0]["source_snapshots"]["osm"]["request"]["query_sha256"],
                query_hash,
            )
            self.assertEqual(
                first[0]["source_snapshots"]["osm"]["raw_source_metadata"],
                {
                    "version": 0.6,
                    "generator": "Overpass API 0.7.62",
                    "osm3s": {"timestamp_osm_base": "2026-09-13T00:00:00Z"},
                },
            )
            self.assertTrue(
                first[0]["source_snapshots"]["osm"]["retrieved_at"].endswith("Z")
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), first)

    def test_offline_pipeline_does_not_reuse_old_wikidata_query_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "venues.json"
            output = root / "resolved.json"
            cache = root / "cache"
            (cache / "wikidata").mkdir(parents=True)
            (cache / "overpass").mkdir()
            source.write_text(json.dumps([STRICT_VENUE]), encoding="utf-8")
            (cache / "wikidata" / f'{VENUE["venue_id"]}.json').write_text(
                json.dumps({"search": [{
                    "id": "Q1", "label": "Wembley Stadium",
                    "description": "association football stadium in London, England",
                }]}), encoding="utf-8"
            )
            result = run_pipeline(source, output, cache, offline=True)[0]

            self.assertEqual(result["status"], "manual_required")
            self.assertEqual(
                result["resolution_reason"], "wikidata_snapshot_unavailable"
            )
            self.assertNotIn("source_snapshots", result)

    def test_offline_pipeline_does_not_reuse_wrong_overpass_query_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "venues.json"
            output = root / "resolved.json"
            cache = root / "cache"
            (cache / "wikidata").mkdir(parents=True)
            (cache / "overpass").mkdir()
            source.write_text(json.dumps([STRICT_VENUE]), encoding="utf-8")
            wikidata_request = build_wikidata_request(STRICT_VENUE)
            wikidata_hash = hashlib.sha256(
                wikidata_request.full_url.encode("utf-8")
            ).hexdigest()
            wikidata_cache = (
                cache / "wikidata"
                / f'{VENUE["venue_id"]}-v2-name-only-{wikidata_hash}.json'
            )
            wikidata_cache.write_text(json.dumps({"search": [{
                "id": "Q1", "label": "Wembley Stadium",
                "description": "association football stadium in London, England",
            }]}), encoding="utf-8")
            (cache / "overpass" / "Q1.json").write_text(
                json.dumps({"elements": []}), encoding="utf-8"
            )
            (cache / "overpass" / "Q1-circuit-stale.json").write_text(
                json.dumps({"elements": []}), encoding="utf-8"
            )

            result = run_pipeline(source, output, cache, offline=True)[0]

            self.assertEqual(result["status"], "manual_required")
            self.assertEqual(result["resolution_reason"], "osm_snapshot_unavailable")
            self.assertNotIn("osm", result["source_snapshots"])


def _polygon_feature(osm_id, tags):
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, **tags},
        "geometry": {"type": "Polygon", "coordinates": [[
            [-0.2, 51.0], [-0.1, 51.0], [-0.1, 51.1],
            [-0.2, 51.1], [-0.2, 51.0],
        ]]},
    }


def _line_feature(osm_id, tags, coordinates=None):
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, **tags},
        "geometry": {"type": "LineString", "coordinates": coordinates or [
            [-0.2, 51.0], [-0.1, 51.1],
        ]},
    }


def _point_feature(osm_id, tags):
    return _point_feature_at(osm_id, tags, -0.15, 51.05)


def _point_feature_at(osm_id, tags, lon, lat):
    return {
        "type": "Feature",
        "properties": {"osm_id": osm_id, **tags},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def _http_error(status, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        "https://example.test/api", status, "test response", headers, None
    )


def _test_client(opener, fake_time, backoff_base=1):
    return JsonHttpClient(
        max_retries=1,
        backoff_base=backoff_base,
        request_interval=0,
        opener=opener,
        sleep=fake_time.sleep,
        monotonic=fake_time.monotonic,
        wall_time=fake_time.time,
    )


class _SequenceOpener:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0
        self.timeouts = []

    def __call__(self, request, timeout):
        self.calls += 1
        self.timeouts.append(timeout)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(json.dumps(result).encode("utf-8"))


class _FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def time(self):
        return 1_700_000_000 + self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


if __name__ == "__main__":
    unittest.main()
