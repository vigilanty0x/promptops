import unittest
from answer_diff.core import compare
class T(unittest.TestCase):
 def test_equal(self): self.assertTrue(compare("Hello","hello")["equal"])
 def test_change(self): self.assertFalse(compare("a b","a c")["equal"])
 def test_ratio(self): self.assertEqual(compare("a","a")["similarity"],1)
 def test_ops(self): self.assertEqual(compare("a","b")["operations"][0]["tag"],"replace")
 def test_counts(self): self.assertEqual(compare("a b","a")["baseline_tokens"],2)
if __name__=="__main__": unittest.main()

