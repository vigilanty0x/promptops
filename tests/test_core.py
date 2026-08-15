import unittest
from consensus_engine.core import decide
class T(unittest.TestCase):
 def test_majority(self): self.assertEqual(decide([{"choice":"a"},{"choice":"a"},{"choice":"b"}])["choice"],"a")
 def test_split(self): self.assertEqual(decide([{"choice":"a"},{"choice":"b"}])["reason"],"split")
 def test_quorum(self): self.assertEqual(decide([{"choice":"a"}],quorum=2)["decision"],"blocked")
 def test_weight(self): self.assertEqual(decide([{"choice":"a","weight":3},{"choice":"b"}])["choice"],"a")
 def test_abstain(self): self.assertEqual(decide([{"choice":"a"},{"choice":"abstain"}])["choice"],"a")
if __name__=="__main__": unittest.main()

