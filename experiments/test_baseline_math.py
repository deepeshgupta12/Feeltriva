"""Small independent checks for the metrics used by the delivered experiment."""
import unittest
import numpy as np
from audit_and_baseline import metrics, norm, digest

class BaselineMetricTests(unittest.TestCase):
    def test_perfect_probabilities(self):
        y=np.array([0,1,2]); p=np.eye(3)
        m,cm,rec,f1,support=metrics(y,p,3)
        self.assertEqual(m['top1_accuracy'],1)
        self.assertEqual(m['macro_f1'],1)
        self.assertEqual(m['brier_multiclass'],0)
        self.assertEqual(m['ece_10_bins'],0)
        self.assertEqual(sum(x['n'] for x in m['calibration_bins']),3)
        np.testing.assert_array_equal(cm,np.eye(3,dtype=int))

    def test_hand_computed_error(self):
        y=np.array([0,1]); p=np.array([[.8,.2],[.6,.4]])
        m,cm,rec,f1,support=metrics(y,p,2)
        self.assertAlmostEqual(m['top1_accuracy'],.5)
        self.assertAlmostEqual(m['macro_f1'],1/3)
        self.assertAlmostEqual(m['balanced_accuracy'],.5)
        self.assertAlmostEqual(m['brier_multiclass'],.4)
        self.assertAlmostEqual(m['ece_10_bins'],.4)
        self.assertAlmostEqual(m['nll'],-np.log(.8*.4)/2)
        np.testing.assert_array_equal(cm,[[1,0],[1,0]])

    def test_bin_boundaries_count_each_case_once(self):
        p=np.array([[.5,.5],[.6,.4],[.7,.3],[.8,.2],[.9,.1],[1,0]])
        m,*_=metrics(np.zeros(6,dtype=int),p,2)
        self.assertEqual(sum(b['n'] for b in m['calibration_bins']),6)

    def test_normalization_preserves_medical_distinctions(self):
        self.assertEqual(norm('  Type 2  DIABETES '),'type 2 diabetes')
        self.assertNotEqual(norm('Type 1 diabetes'),norm('Type 2 diabetes'))
        self.assertNotEqual(digest(['ab','c']),digest(['a','bc']))

if __name__=='__main__':
    unittest.main()
