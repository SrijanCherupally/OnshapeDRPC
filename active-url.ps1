param([string]$WindowTitle, [switch]$Serve)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
function Read-OnshapeState([string]$WindowTitle) {
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
                $taskState = @{ url = $taskUrl; part_studio = $false; feature = $null; available = $true }
                $taskFeatureListCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'feature-list')
                $taskFeatureList = $taskDocument.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $taskFeatureListCondition)
                $taskState.part_studio = $null -ne $taskFeatureList
                if ($taskState.part_studio) {
                    $taskDialogCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'feature-dialog')
                    $taskDialog = $taskDocument.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $taskDialogCondition)
                    if ($null -ne $taskDialog) {
                        $taskTextCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Text)
                        $taskFirstText = $taskDialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $taskTextCondition)
                        $taskFeatureName = if ($taskFirstText) { $taskFirstText.Current.Name } else { '' }
                        $taskHelpUrl = ''
                        $taskLinkCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Hyperlink)
                        $taskLinks = $taskDialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, $taskLinkCondition)
                        foreach ($taskLink in $taskLinks) {
                            $taskLinkValue = $null
                            if ($taskLink.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$taskLinkValue)) {
                                if ($taskLinkValue.Current.Value -match '^https://cad\.onshape\.com/help/') {
                                    $taskHelpUrl = $taskLinkValue.Current.Value
                                    break
                                }
                            }
                        }
                        $taskState.feature = @{ name = $taskFeatureName; help_url = $taskHelpUrl }
                    }
                }
                return $taskState
            }
        }
    }
}
return @{ url = ''; part_studio = $false; feature = $null; available = $false }
}
if ($Serve) {
    while ($null -ne ($taskLine = [Console]::ReadLine())) {
        try {
            $taskRequest = $taskLine | ConvertFrom-Json
            $taskResult = Read-OnshapeState $taskRequest.title
            if ($taskRequest.state) {
                [Console]::WriteLine(($taskResult | ConvertTo-Json -Compress -Depth 4))
            } else {
                [Console]::WriteLine([string]$taskResult.url)
            }
        } catch {
            [Console]::WriteLine('')
        }
    }
} else {
    (Read-OnshapeState $WindowTitle).url
}
