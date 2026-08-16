import unittest
from pathlib import Path
class Contract(unittest.TestCase):
 def test_phased_owner_exists(self):
  self.assertTrue((Path(__file__).parent/'phased_h100_owner.py').is_file())
if __name__=='__main__':unittest.main()
