Option Explicit

Dim fso, shell, dir, pythonw, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Use the folder this script lives in, so it works from any location.
dir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = dir & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    pythonw = "pythonw.exe"
End If

cmd = """" & pythonw & """ """ & dir & "\run_server.py"""
shell.CurrentDirectory = dir
' 0 = hidden window, False = don't wait for the process to finish.
shell.Run cmd, 0, False
