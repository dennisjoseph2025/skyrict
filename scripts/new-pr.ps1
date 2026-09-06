#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Opens the GitHub "New pull request" page for the current branch with a
  title pre-filled to the repo's PR-title convention.

.DESCRIPTION
  Builds a compare URL against the base branch (default dev) and opens it in
  the default browser with the title pre-filled. The convention is enforced
  by the `Validate PR Title` workflow:

    1. Jira-tracked work: [INTERNAL-ID]: type(scope)/TICKET-KEY summary
                          e.g. [RPT-DATA-001]: feat(core)/SKY-77 reporting data layer - ...
    2. Non-Jira work:     type(scope): summary  (Conventional Commits, no ID/key)
                          e.g. fix(ci): validate root CI - ...

  - If the current branch name contains a Jira key (e.g. SKY-78), the title is
    pre-filled as "[DOMAIN-LAYER-000]: type/SKY-78 <summary>" and you replace the
    [DOMAIN-LAYER-000] internal-ID placeholder with the real ID.
  - Otherwise a plain conventional title is built. Non-Jira PRs simply use it.

.PARAMETER Labels
  Comma-separated labels to pre-apply, e.g. "area: core". Optional.

.PARAMETER Base
  Base branch to compare against (default dev).

.PARAMETER NoBrowser
  Print the URL instead of opening the browser.
#>
param(
    [string]$Labels = "",
    [string]$Base = "dev",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Repo = "nkswalih/skyrict"
$ValidTypes = @("feat", "fix", "chore", "docs", "test", "refactor", "perf", "ci", "build")

function Get-CurrentBranch {
    $Branch = (git branch --show-current 2>$null)
    if (-not $Branch) { throw "Not on a git branch. Run this script from inside the repo." }
    return $Branch.Trim()
}

function Get-TypeFromBranch([string]$Branch) {
    $First = $Branch.Split('/')[0].ToLower()
    if ($ValidTypes -contains $First) { return $First }
    return $ValidTypes[0] # "feat" - conventional default; paste a Jira ID prefix when tracking work
}

function Get-JiraKey([string]$Branch) {
    # Matches a project key like SKY-78 anywhere in the branch name.
    if ($Branch -match '[A-Z]{2,6}-[0-9]{2,5}') { return $Matches[0] }
    return $null
}

function Get-Summary([string]$Branch, [string]$Type, [string]$JiraKey) {
    $Tail = $Branch
    if ($Tail -match '^' + [regex]::Escape($Type) + '/') { $Tail = $Tail.Substring($Type.Length + 1) }
    if ($JiraKey -and $Tail -match '^' + [regex]::Escape($JiraKey) + '-?') { $Tail = $Tail.Substring($Matches[0].Length) }
    $Tail = ($Tail -replace '[-_]+', ' ').Trim()
    if (-not $Tail) { $Tail = "describe this change" }
    return $Tail
}

function New-Title {
    param([string]$Branch)
    $Type = Get-TypeFromBranch -Branch $Branch
    $JiraKey = Get-JiraKey -Branch $Branch
    $Summary = Get-Summary -Branch $Branch -Type $Type -JiraKey $JiraKey
    if ($JiraKey) {
        # Jira-tracked work: internal ID + ticket key (internal ID is a placeholder the author fills in).
        return "[DOMAIN-LAYER-000]: $Type/$JiraKey $Summary"
    }
    return "${Type}: $Summary"
}

$Branch = Get-CurrentBranch
$Title = New-Title -Branch $Branch

$Query = [System.Collections.Generic.List[string]]::new()
$Query.Add("quick_pull=1")
$Query.Add("title=" + [uri]::EscapeDataString($Title))
if ($Labels) { $Query.Add("labels=" + [uri]::EscapeDataString($Labels)) }

$Url = "https://github.com/$Repo/compare/$Base...$Branch" + "?" + ($Query -join "&")

Write-Host ""
Write-Host "  Branch : $Branch" -ForegroundColor Green
Write-Host "  Title  : $Title" -ForegroundColor Green
Write-Host "  URL    : $Url" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  $Branch title guide:" -ForegroundColor Cyan
Write-Host "    Jira work : [RPT-DATA-001]: type(scope)/SKY-78 summary   (replace [DOMAIN-LAYER-000])" -ForegroundColor Cyan
Write-Host "    Non-Jira  : fix(ci): validate root CI - ...              (delete the [ID]: prefix)" -ForegroundColor Cyan
Write-Host ""

if ($NoBrowser) { return }

# Windows/macOS/Linux friendly open.
if ($IsWindows) {
    Start-Process $Url
} elseif ($IsMacOS) {
    & open $Url
} else {
    & xdg-open $Url
}