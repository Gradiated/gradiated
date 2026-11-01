import unittest

from reference_queries import normalize_team


class ReferenceScope(unittest.TestCase):
    def test_preserves_business_numbers_and_strings(self):
        sql = "SELECT 42, 'team_id = 42', 'order-42' FROM events WHERE team_id = 42 AND amount = 42"
        self.assertEqual(normalize_team(sql, 42), sql.replace("WHERE team_id = 42", "WHERE team_id = {team}"))

    def test_scopes_aliases_but_not_other_columns_or_teams(self):
        sql = "WHERE e.team_id=42 AND other_team_id=42 AND team_id = 420 AND price = 42.5"
        self.assertEqual(normalize_team(sql, 42), sql.replace("e.team_id=42", "e.team_id={team}"))

    def test_comments_and_escaped_literals_are_preserved(self):
        sql = "SELECT 'it''s team_id = 42' /* team_id = 42 */ -- team_id = 42\n WHERE team_id=42"
        self.assertEqual(normalize_team(sql, 42), sql.replace("WHERE team_id=42", "WHERE team_id={team}"))

    def test_existing_placeholder_does_not_skip_other_literal_scopes(self):
        self.assertEqual(normalize_team("team_id={team} OR team_id=42", 42), "team_id={team} OR team_id={team}")


if __name__ == "__main__":
    unittest.main()
