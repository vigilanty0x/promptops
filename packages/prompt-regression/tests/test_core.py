import unittest
from prompt_regression.core import compare
class T(unittest.TestCase):
 def test_regression(self): self.assertEqual(compare([{"id":"x","baseline":"ok","candidate":"bad","expected":"ok"}])["regressions"],1)
 def test_improve(self): self.assertEqual(compare([{"id":"x","baseline":"bad","candidate":"ok","expected":"ok"}])["results"][0]["status"],"improvement")
 def test_contains(self): self.assertEqual(compare([{"id":"x","baseline":"hello x","candidate":"hello x","expected":"x","mode":"contains"}])["regressions"],0)
 def test_json(self): self.assertEqual(compare([{"id":"x","baseline":"{}","candidate":"{}","expected":{},"mode":"json"}])["regressions"],0)
 def test_empty(self):
  with self.assertRaises(ValueError): compare([])
if __name__=="__main__": unittest.main()

