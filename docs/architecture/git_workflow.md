# Git Workflow

## Branch Strategy

### Main Branches
- `main` - Production-ready code
- `develop` - Integration branch for features

### Supporting Branches
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Production hotfixes
- `docs/*` - Documentation updates

## Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style changes
- `refactor` - Code refactoring
- `test` - Test additions/changes
- `chore` - Build/dependency updates

### Example
```
feat(agents): add agent creation endpoint

- Implement POST /agents endpoint
- Add agent validation schema
- Add database migration

Closes #123
```

## Pull Request Process

1. Create feature branch from `develop`
2. Make commits with clear messages
3. Push to remote and create PR
4. Request code review
5. Address feedback
6. Merge to `develop` after approval
7. Delete feature branch

## Release Process

1. Create release branch from `develop`
2. Update version numbers
3. Update CHANGELOG
4. Merge to `main` with tag
5. Merge back to `develop`
