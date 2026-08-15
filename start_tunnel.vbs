Option Explicit

Dim fso, shell, dir, cf, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

If Not fso.FileExists(cf) Then
    cf = "cloudflared.exe"
End If

cmd = "cmd /c """ & cf & """ tunnel --url http://127.0.0.1:8000 --no-autoupdate >> """ & dir & "\tunnel.log"" 2>&1"
shell.CurrentDirectory = dir
' 0 = hidden window, False = don't wait for the process to finish.
shell.Run cmd, 0, False
