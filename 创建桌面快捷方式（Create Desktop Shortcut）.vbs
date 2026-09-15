' 在桌面创建"宝可梦翻译工具"快捷方式
Option Explicit

Dim fso, shell, scriptDir, desktop, lnkPath, target, iconPath

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktop   = shell.SpecialFolders("Desktop")
lnkPath   = desktop & "\宝可梦翻译工具.lnk"
target    = scriptDir & "\启动（Start）.bat"
iconPath  = scriptDir & "\start.ico"

If Not fso.FileExists(target) Then
    MsgBox "未找到 启动（Start）.bat：" & target, 16, "错误"
    WScript.Quit 1
End If

Dim lnk
Set lnk = shell.CreateShortcut(lnkPath)
lnk.TargetPath       = target
lnk.WorkingDirectory = scriptDir
lnk.Description      = "宝可梦同人游戏翻译工具"
lnk.WindowStyle      = 1
If fso.FileExists(iconPath) Then
    lnk.IconLocation = iconPath
End If
lnk.Save

MsgBox "已在桌面创建快捷方式：" & vbCrLf & lnkPath, 64, "完成"
