param([string]$WindowTitle)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$taskRoot = [System.Windows.Automation.AutomationElement]::RootElement
$taskWindows = $taskRoot.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($taskWindow in $taskWindows) {
    if ($taskWindow.Current.Name -ne $WindowTitle) { continue }
    # Chromium exposes the selected page URL through its Document ValuePattern,
    # including installed apps without a visible address bar.
    $taskCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document)
    $taskDocuments = $taskWindow.FindAll([System.Windows.Automation.TreeScope]::Descendants, $taskCondition)
    foreach ($taskDocument in $taskDocuments) {
        $taskValue = $null
        if ($taskDocument.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$taskValue)) {
            $taskUrl = $taskValue.Current.Value
            if ($taskUrl -match '^https://cad\.onshape\.com/documents/[a-f0-9]{24}/[wvm]/[a-f0-9]{24}/e/[a-f0-9]{24}') {
                Write-Output $taskUrl
                exit
            }
        }
    }
}
