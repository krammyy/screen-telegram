' Silent launcher: no console window at all
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
stopFlag = dir & "\stop.flag"
If fso.FileExists(stopFlag) Then fso.DeleteFile stopFlag, True
sh.CurrentDirectory = dir
' 0 = hidden window
sh.Run "pythonw """ & dir & "\watchdog.py""", 0, False
