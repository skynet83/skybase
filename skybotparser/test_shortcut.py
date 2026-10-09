import os
import subprocess
import tempfile

def create_shortcut(target_exe, shortcut_path, icon_path=None, description="SkyBotParser"):
    vbs_content = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_exe}"
oLink.WorkingDirectory = "{os.path.dirname(target_exe)}"
oLink.Description = "{description}"
'''
    if icon_path and os.path.exists(icon_path):
        vbs_content += f'oLink.IconLocation = "{icon_path}, 0"\n'
    vbs_content += 'oLink.Save\n'

    vbs_file = os.path.join(tempfile.gettempdir(), "_mksnk.vbs")
    with open(vbs_file, "w", encoding="cp1251") as f:
        f.write(vbs_content)
    try:
        subprocess.run(["cscript", "//nologo", vbs_file], check=True)
    finally:
        if os.path.exists(vbs_file):
            os.remove(vbs_file)

if __name__ == "__main__":
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    test_lnk = os.path.join(desktop, "SkyBot_Test.lnk")
    icon = r"C:\G\ins\Avito-Parser3\skybase\img\skybase.ico"
    create_shortcut("notepad.exe", test_lnk, icon)
    print("Shortcut exists:", os.path.exists(test_lnk))
    if os.path.exists(test_lnk):
        os.remove(test_lnk)
        print("Test shortcut cleaned up successfully.")
