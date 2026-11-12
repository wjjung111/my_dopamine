' WJ Calendar launcher: starts the server hidden (if not running) and opens it in an Ego Lite app window.
' Argument /server only starts the server (used by the Startup shortcut).
Option Explicit
Dim sh, fso, base, url, ego, http, up, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
url = "http://127.0.0.1:8765/"

Function IsUp()
  On Error Resume Next
  Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  http.setTimeouts 500, 500, 500, 500
  http.open "GET", url & "api/rev", False
  http.send
  IsUp = (Err.Number = 0 And http.status = 200)
  On Error GoTo 0
End Function

If Not IsUp() Then
  sh.CurrentDirectory = base
  sh.Run """" & base & "\.venv\Scripts\pythonw.exe"" """ & base & "\server.py""", 0, False
  For i = 1 To 30
    WScript.Sleep 200
    If IsUp() Then Exit For
  Next
End If

If WScript.Arguments.Count > 0 Then
  If LCase(WScript.Arguments(0)) = "/server" Then WScript.Quit
End If

ego = "C:\Program Files\Citro Labs\ego lite\Application\ego.exe"
If fso.FileExists(ego) Then
  sh.Run """" & ego & """ --app=" & url, 1, False
Else
  sh.Run url, 1, False
End If
