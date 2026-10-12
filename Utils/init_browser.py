import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# cd = os.path.join(os.path.dirname(sys.executable), "chrome-dir")
cd = rf"{BASE_DIR}\chrome-dir"
os.system(f"start \"\" \"{chrome_path}\" --user-data-dir=\"{cd}\" --window-position=0,0")
