import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text

from backend.app.product_services.news_monitor import NewsMonitorService


class NewsMonitorServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name) / "news_sources.json"
        self.db_path = Path(self.temp_dir.name) / "news_monitor.sqlite"
        self.engine = create_engine(f"sqlite+pysqlite:///{self.db_path}")
        self.addCleanup(self.engine.dispose)

    def _service(self, sources, fetch_map):
        self.config_path.write_text(json.dumps(sources), encoding="utf-8")
        return NewsMonitorService(
            engine=self.engine,
            connection_string=f"sqlite+pysqlite:///{self.db_path}",
            config_path=self.config_path,
            fetcher=lambda url: fetch_map[url],
        )

    def test_completed_run_skips_without_force(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Player questionable with ankle injury</title>
                <link>https://example.com/1</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Limited in practice.</description>
                <guid>a1</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        first = service.run_daily(run_date=date(2026, 6, 20))
        second = service.run_daily(run_date=date(2026, 6, 20))

        self.assertEqual(first.status, "completed")
        self.assertFalse(first.skipped)
        self.assertEqual(second.status, "skipped")
        self.assertTrue(second.skipped)
        self.assertEqual(first.run_id, second.run_id)

        with self.engine.begin() as conn:
            item_count = conn.execute(text("SELECT COUNT(*) FROM news_monitor_item")).scalar()
            signal_count = conn.execute(text("SELECT COUNT(*) FROM news_monitor_signal")).scalar()
        self.assertEqual(item_count, 1)
        self.assertEqual(signal_count, 1)

    def test_manual_note_generates_signal(self):
        service = self._service(
            sources=[
                {
                    "source_id": "manual_notes",
                    "name": "Manual Notes",
                    "source_type": "manual",
                    "url": None,
                    "enabled": True,
                    "content_mode": "manually_provided_text",
                    "notes": "",
                }
            ],
            fetch_map={},
        )

        service.add_manual_note(
            run_date=date(2026, 6, 21),
            title="Bills WR Khalil Shakir update",
            note_text="Coach said the backup WR is getting first-team reps and Khalil Shakir could start for the Buffalo Bills.",
            source_link="https://example.com/note",
        )
        result = service.run_daily(run_date=date(2026, 6, 21))

        self.assertEqual(result.items_ingested, 1)
        self.assertEqual(result.signals_extracted, 2)
        self.assertTrue(result.report["depth_chart_notes"])
        self.assertTrue(result.report["manual_review"])
        self.assertFalse(result.report["roster_moves"])
        self.assertEqual(result.report["depth_chart_notes"][0]["player_name"], "Khalil Shakir")
        self.assertEqual(result.report["depth_chart_notes"][0]["team"], "BUF")

    def test_get_report_returns_route_compatible_payload(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Player questionable with ankle injury</title>
                <link>https://example.com/1</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Limited in practice.</description>
                <guid>a1</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        service.run_daily(run_date=date(2026, 6, 23))
        report = service.get_report(date(2026, 6, 23))

        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report["skipped"])
        self.assertIn("message", report)
        self.assertEqual(report["status"], "completed")

    def test_feedback_upsert_and_clear_round_trip(self):
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": b"<rss><channel></channel></rss>"},
        )

        first = service.upsert_feedback(
            run_date=date(2026, 6, 24),
            signal_key="2026-06-24|injury|Player questionable|||",
            signal_type="injury_update",
            signal_text="Player questionable",
            player_name="Test Player",
            team="buf",
            source_link="https://example.com/injury",
            feedback_choice="Relevant",
            note_text="Worth monitoring near lock.",
        )
        second = service.upsert_feedback(
            run_date=date(2026, 6, 24),
            signal_key="2026-06-24|injury|Player questionable|||",
            signal_type="injury_update",
            signal_text="Player questionable",
            player_name="Test Player",
            team="BUF",
            source_link="https://example.com/injury",
            feedback_choice="Valuable",
            note_text="This should move the slate.",
        )

        rows = service.list_feedback(date(2026, 6, 24))

        self.assertEqual(first["signal_key"], second["signal_key"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feedback_choice"], "Valuable")
        self.assertEqual(rows[0]["note_text"], "This should move the slate.")
        self.assertEqual(rows[0]["team"], "BUF")
        self.assertEqual(rows[0]["feedback_id"], first["feedback_id"])

        cleared = service.upsert_feedback(
            run_date=date(2026, 6, 24),
            signal_key="2026-06-24|injury|Player questionable|||",
            signal_type="injury_update",
            signal_text="Player questionable",
            feedback_choice=None,
            note_text="",
        )

        self.assertEqual(cleared["feedback_choice"], None)
        self.assertEqual(service.list_feedback(date(2026, 6, 24)), [])

    def test_rss_signal_extracts_player_and_team(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Chiefs TE Travis Kelce expected to be limited at minicamp</title>
                <link>https://example.com/kelce</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Kansas City Chiefs star Travis Kelce is managing a knee issue.</description>
                <guid>kelce1</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 6, 24))

        self.assertEqual(result.items_ingested, 1)
        injury_signal = result.report["injury_updates"][0]
        self.assertEqual(injury_signal["player_name"], "Travis Kelce")
        self.assertEqual(injury_signal["team"], "KC")
        self.assertTrue(injury_signal["signal_text"].startswith("Travis Kelce (KC):"))

    def test_rss_filters_out_college_and_fantasy_links(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Source: Big 12 monitoring Sorsby fallout, options</title>
                <link>https://www.espn.com/college-football/story/_/id/1/example</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>College football story that should be ignored.</description>
                <guid>a1</guid>
            </item>
            <item>
                <title>2026 Fantasy Football Draft Guide</title>
                <link>https://www.espn.com/fantasy/football/story/_/id/2/example</link>
                <pubDate>Sat, 20 Jun 2026 10:05:00 GMT</pubDate>
                <description>Evergreen fantasy guide that should be ignored.</description>
                <guid>a2</guid>
            </item>
            <item>
                <title>Bowles confirms Bucs' Vea a minicamp hold-in</title>
                <link>https://www.espn.com/nfl/story/_/id/3/example</link>
                <pubDate>Sat, 20 Jun 2026 10:10:00 GMT</pubDate>
                <description>Bucs defensive tackle Vita Vea is not physically participating in practice.</description>
                <guid>a3</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 6, 25))

        self.assertEqual(result.items_ingested, 1)
        self.assertEqual(len(result.report["team_headlines"]), 1)
        self.assertIn("Vea", result.report["team_headlines"][0]["title"])

    def test_generic_monitoring_does_not_trigger_injury_signal(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>League monitoring quarterback situation</title>
                <link>https://www.espn.com/nfl/story/_/id/4/example</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Front office is monitoring several options ahead of camp.</description>
                <guid>a4</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 6, 26))

        self.assertFalse(result.report["injury_updates"])
        self.assertFalse(result.report["manual_review"])

    def test_evergreen_nfl_story_is_stored_but_filtered_from_report(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Ranking the top 10 NFL offseasons: Rams loaded after blockbuster trade</title>
                <link>https://www.cbssports.com/nfl/news/ranking-top-10-nfl-offseasons-myles-garrett-trade/</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>An offseason ranking story that should not hit the DFS-facing report.</description>
                <guid>a5</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 6, 29))

        self.assertEqual(result.items_ingested, 1)
        self.assertEqual(result.signals_extracted, 1)
        self.assertFalse(result.report["high_priority_signals"])
        self.assertFalse(result.report["team_headlines"])

    def test_roundup_contract_story_does_not_surface_as_roster_move(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>What we're hearing on 32 NFL contract negotiations...</title>
                <link>https://www.espn.com/nfl/story/_/id/1/contracts</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Our reporters have the latest buzz on 32 contract extension candidates -- one from every team.</description>
                <guid>a6</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 6, 30))

        self.assertFalse(result.report["roster_moves"])
        self.assertFalse(result.report["team_headlines"])

    def test_legitimacy_story_does_not_surface_as_injury(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Let's judge the legitimacy of five NFL players who changed course</title>
                <link>https://www.espn.com/nfl/story/_/id/2/legitimacy</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Daniel Jones and George Pickens came out of nowhere in 2025. Are these abrupt performance changes real?</description>
                <guid>a7</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 7, 1))

        self.assertFalse(result.report["injury_updates"])
        self.assertFalse(result.report["team_headlines"])

    def test_surprise_players_roundup_does_not_match_out_status(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>32 teams, 32 surprises: Which players stood out on offense and defense</title>
                <link>https://www.espn.com/nfl/story/_/id/3/surprises</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>An offseason roundup looking at who stood out across the league.</description>
                <guid>a10</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 7, 3))

        self.assertFalse(result.report["injury_updates"])
        self.assertFalse(result.report["high_priority_signals"])

    def test_qb_tiers_story_does_not_surface_as_depth_chart_news(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Ranking NFL starting quarterbacks by tiers ahead of the 2026 season</title>
                <link>https://www.cbssports.com/nfl/news/nfl-quarterback-rankings-2026-tiers/</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>The gap between the league's elite, rising stars and stopgap starters remains fascinating.</description>
                <guid>a11</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 7, 4))

        self.assertFalse(result.report["depth_chart_notes"])
        self.assertFalse(result.report["high_priority_signals"])

    def test_retirement_and_free_agency_story_does_not_surface_as_injury(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Joey Bosa retirement rumors continue as teams monitor his future</title>
                <link>https://www.cbssports.com/nfl/news/joey-bosa-retirement-nfl/</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>The pass rusher is contemplating retirement after injuries earlier in his career.</description>
                <guid>a12</guid>
            </item>
            <item>
                <title>DeAndre Hopkins staying patient in free agency search for a new team</title>
                <link>https://www.cbssports.com/nfl/news/deandre-hopkins-free-agency-landing-spots/</link>
                <pubDate>Sat, 20 Jun 2026 10:05:00 GMT</pubDate>
                <description>The veteran receiver will not force a signing this season.</description>
                <guid>a13</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 7, 5))

        self.assertFalse(result.report["injury_updates"])
        self.assertFalse(result.report["roster_moves"])
        self.assertFalse(result.report["high_priority_signals"])

    def test_team_headlines_only_include_actionable_topics(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Jaguars, TE Strange agree to 3-year extension</title>
                <link>https://www.espn.com/nfl/story/_/id/1/strange-extension</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>The Jaguars and tight end Brenton Strange agreed to a three-year extension.</description>
                <guid>a8</guid>
            </item>
            <item>
                <title>Inside the Bills' new $2.1 billion stadium</title>
                <link>https://www.espn.com/nfl/story/_/id/2/bills-stadium</link>
                <pubDate>Sat, 20 Jun 2026 10:05:00 GMT</pubDate>
                <description>A look inside the new stadium project.</description>
                <guid>a9</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        result = service.run_daily(run_date=date(2026, 7, 2))

        self.assertEqual(len(result.report["team_headlines"]), 1)
        self.assertIn("Strange", result.report["team_headlines"][0]["title"])

    def test_deduped_item_can_create_signals_for_new_run_date(self):
        rss = b"""
        <rss><channel>
            <item>
                <title>Chiefs TE Travis Kelce expected to be limited at minicamp</title>
                <link>https://example.com/kelce</link>
                <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
                <description>Kansas City Chiefs star Travis Kelce is managing a knee issue.</description>
                <guid>kelce1</guid>
            </item>
        </channel></rss>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "rss_news",
                    "name": "RSS News",
                    "source_type": "rss",
                    "url": "https://feed.test/rss",
                    "enabled": True,
                    "content_mode": "metadata_only",
                    "notes": "",
                }
            ],
            fetch_map={"https://feed.test/rss": rss},
        )

        first = service.run_daily(run_date=date(2026, 6, 27))
        second = service.run_daily(run_date=date(2026, 6, 28), force=True)

        self.assertEqual(first.items_ingested, 1)
        self.assertEqual(second.items_ingested, 0)
        self.assertGreaterEqual(second.signals_extracted, 1)
        self.assertTrue(second.report["injury_updates"])

    def test_import_history_from_json_uses_seeded_entities(self):
        service = self._service(sources=[], fetch_map={})
        history_path = Path(self.temp_dir.name) / "history.json"
        history_path.write_text(
            json.dumps(
                [
                    {
                        "title": "Rhamondre Stevenson questionable for Sunday",
                        "summary": "Limited in practice with an ankle injury.",
                        "link": "https://example.com/rhamondre",
                        "published_at": "2025-10-11T14:00:00Z",
                        "player_name": "Rhamondre Stevenson",
                        "team": "NE",
                    }
                ]
            ),
            encoding="utf-8",
        )

        result = service.import_history(path=str(history_path), run_date=date(2025, 10, 11))

        self.assertEqual(result.items_ingested, 1)
        self.assertEqual(result.signals_extracted, 1)
        signal = result.report["injury_updates"][0]
        self.assertEqual(signal["player_name"], "Rhamondre Stevenson")
        self.assertEqual(signal["team"], "NE")

    def test_import_history_from_csv(self):
        service = self._service(sources=[], fetch_map={})
        history_path = Path(self.temp_dir.name) / "history.csv"
        history_path.write_text(
            "title,summary,link,published_at\n"
            "\"Titans sign depth running back\",\"Team signed a reserve RB after minicamp.\",\"https://example.com/titans\",\"2025-08-01T12:00:00Z\"\n",
            encoding="utf-8",
        )

        result = service.import_history(path=str(history_path), run_date=date(2025, 8, 1))

        self.assertEqual(result.items_ingested, 1)
        self.assertEqual(result.sources_checked, 1)
        self.assertTrue(result.report["roster_moves"])

    def test_injury_table_creates_high_confidence_injury_signal(self):
        html = b"""
        <table>
            <thead>
                <tr>
                    <th>Player</th><th>Team</th><th>Position</th><th>Injury</th>
                    <th>Practice Status</th><th>Game Status</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Jane Runner</td><td>BUF</td><td>RB</td><td>Hamstring</td>
                    <td>DNP</td><td>Questionable</td>
                </tr>
            </tbody>
        </table>
        """
        service = self._service(
            sources=[
                {
                    "source_id": "injuries",
                    "name": "Injuries",
                    "source_type": "injury_table",
                    "url": "https://feed.test/injuries",
                    "enabled": True,
                    "content_mode": "factual_table_only",
                    "notes": "",
                    "options": {
                        "table_index": 0,
                        "column_map": {
                            "Player": "player_name",
                            "Team": "team",
                            "Position": "position",
                            "Injury": "injury",
                            "Practice Status": "practice_status",
                            "Game Status": "game_status",
                        },
                    },
                }
            ],
            fetch_map={"https://feed.test/injuries": html},
        )

        result = service.run_daily(run_date=date(2026, 6, 22))

        self.assertEqual(result.items_ingested, 1)
        self.assertEqual(result.signals_extracted, 1)
        signal = result.report["injury_updates"][0]
        self.assertEqual(signal["confidence"], "high")
        self.assertEqual(signal["dfs_relevance"], "high")
        self.assertIn("Jane Runner", signal["signal_text"])


if __name__ == "__main__":
    unittest.main()
