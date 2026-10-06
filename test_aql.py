import unittest
from aql import calculate, code_for, plan_for

class AQLTableTests(unittest.TestCase):
    def test_required_anchors(self):
        self.assertEqual((125,3,4), tuple(plan_for("K","1.0")[k] for k in ("size","ac","re")))
        self.assertEqual((80,5,6), tuple(plan_for("J","2.5")[k] for k in ("size","ac","re")))
        self.assertEqual((200,5,6), tuple(plan_for("L","1.0")[k] for k in ("size","ac","re")))

    def test_table_i_edges(self):
        self.assertEqual("A", code_for(8,"II"))
        self.assertEqual("B", code_for(9,"II"))
        self.assertEqual("Q", code_for(500001,"II"))
        self.assertEqual("R", code_for(500001,"III"))

    def test_full_inspection_rule(self):
        result=calculate(1000,"II","0.010","1.5","4.0")
        self.assertEqual(1000,result["sample_size"])
        self.assertEqual("100%",result["code_letter"])
        self.assertEqual((0,1),(result["criteria"]["cri"]["ac"],result["criteria"]["cri"]["re"]))

if __name__=="__main__": unittest.main()
