<!--
PR title is enforced by the Validate PR Title workflow and must match one of:
  1. Jira-tracked work:  [INTERNAL-ID]: type(scope)/TICKET-KEY summary
                         e.g. [RPT-DATA-001]: feat(core)/SKY-77 reporting data layer - ...
  2. Non-Jira work:      type(scope): summary  (Conventional Commits, no ID/key)
                         e.g. fix(ci): validate root CI - ...
Types: feat|fix|chore|docs|test|refactor|perf|ci|build -- scope optional -- breaking: type! or type(scope)!:
See CONTRIBUTING.md, "Pull Request Process" -> "PR Title".
-->

## Summary

<!-- What does this PR do? One sentence. -->

Closes #

## Change Type

<!-- Check one. -->

- [ ] `feat` - New feature
- [ ] `fix` - Bug fix
- [ ] `refactor` - Code restructuring (no behavior change)
- [ ] `docs` - Documentation only
- [ ] `test` - Adding or updating tests
- [ ] `chore` - Build, CI, dependencies, tooling
- [ ] `perf` - Performance improvement
- [ ] `ci` - CI/CD changes

## What Changed

<!-- Bullet points. What was added, changed, or removed? -->

-

## Why

<!-- Motivation. Link to issue or ADR if applicable. -->

## Testing

<!-- How was this tested? What tests were added? -->

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated (if applicable)
- [ ] Manual testing performed (describe below)

## Checklist

- [ ] Code follows the project's style guidelines (`make lint` passes)
- [ ] Self-review completed
- [ ] Tests pass (`make test`)
- [ ] Documentation updated (if API or behavior change)
- [ ] No breaking changes (or justified in the summary)
- [ ] Domain events emitted correctly (if applicable)
- [ ] No secrets, credentials, or `.env` values committed
