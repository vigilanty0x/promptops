import unittest
from model_scorecard.core import score
class T(unittest.TestCase):
 def data(self): return [{"model":"a","runs":[{"passed":True,"latency_ms":10,"cost":.1}]},{"model":"b","runs":[{"passed":False,"latency_ms":5,"cost":.01}]}]
 def test_winner(self): self.assertEqual(score(self.data())["winner"],"a")
 def test_pass_rate(self): self.assertEqual(score(self.data())["scorecards"][0]["pass_rate"],1)
 def test_cost_gate(self): self.assertIsNone(score(self.data()[:1],max_cost=.01)["winner"])
 def test_latency_gate(self): self.assertFalse(score(self.data()[:1],max_latency_ms=1)["scorecards"][0]["eligible"])
 def test_empty(self):
  with self.assertRaises(ValueError): score([])
if __name__=="__main__": unittest.main()

