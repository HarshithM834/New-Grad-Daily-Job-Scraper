"""Regression tests for optional conservative graduate filtering."""
import unittest
from entry_level import classify_role, select_categories


class EntryLevelTests(unittest.TestCase):
    def test_unmistakable_graduate_role(self):
        for role in ("2027 University Graduate - Software Engineer", "Junior Data Engineer", "Entry-Level Backend Developer", "Software Engineer I", "Associate Software Engineer", "Early Career ML Engineer"):
            with self.subTest(role=role):
                self.assertEqual(classify_role(role), "likely")

    def test_seniority_overrides_graduate_keywords(self):
        for role in ("Senior Junior Software Engineer", "Staff Data Engineer", "Principal Machine Learning Engineer", "Engineering Manager, New Graduate Program"):
            with self.subTest(role=role):
                self.assertEqual(classify_role(role), "unlikely")

    def test_ambiguous_roles_remain_visible_by_default(self):
        self.assertEqual(classify_role("Software Engineer"), "unknown")
        self.assertEqual(classify_role("AI Research Scientist"), "unknown")

    def test_categories_are_validated(self):
        self.assertEqual(select_categories("all"), ("SWE", "DE", "AI/ML"))
        self.assertEqual(select_categories("swe, ai/ml, SWE"), ("SWE", "AI/ML"))
        self.assertEqual(select_categories("Data engineering"), ("DE",))
        with self.assertRaisesRegex(ValueError, "Unsupported category"):
            select_categories("finance")

if __name__ == "__main__":
    unittest.main()