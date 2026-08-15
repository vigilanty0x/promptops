import unittest
from llm_jury.core import judge
class T(unittest.TestCase):
 def test_pass(self): self.assertEqual(judge([.8,.9])["decision"],"pass")
 def test_fail(self): self.assertEqual(judge([.2,.4])["decision"],"fail")
 def test_disagreement(self): self.assertEqual(judge([0,1])["decision"],"blocked")
 def test_median(self): self.assertEqual(judge([.2,.8,.9])["median"],.8)
 def test_bounds(self):
  with self.assertRaises(ValueError): judge([2,0])
if __name__=="__main__": unittest.main()

