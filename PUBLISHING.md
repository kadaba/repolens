# Publishing `app-classifier` to PyPI

Step-by-step guide to get from "code on my laptop" to `pip install app-classifier` working for anyone in the world.

**Time budget:** ~30 minutes the first time, ~3 minutes for every release after.

---

## Pre-flight checks (do these once, before your first release)

### 1. Verify the package name is available

```bash
# If this returns "Not Found" you're good. If it shows a package, the name is taken.
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/app-classifier/json
```

- `404` → name is free, you can use it
- `200` → name is already taken on PyPI; either pick a different name or contact the existing maintainer

**Heads up:** `app-classifier` is generic enough that there may be a squatted or abandoned package. Check before you commit to the name. If it's taken, your fallback options are:
- `app-classifier-py` (less ideal but works)
- `repolens` (the brand name I suggested in LAUNCH.md)
- `whatdoes`

### 2. Create PyPI accounts

You need TWO accounts — they're separate systems with separate logins:

1. **TestPyPI** (staging): https://test.pypi.org/account/register/
2. **PyPI** (production): https://pypi.org/account/register/

Always test on TestPyPI before pushing to real PyPI. **A version once uploaded to PyPI can NEVER be re-uploaded** (even after deletion). Bugs in your `0.1.0` release mean shipping `0.1.1`, not "fixing 0.1.0."

### 3. Enable 2FA on both accounts

PyPI requires 2FA for all uploads as of 2024. Set it up at:
- https://test.pypi.org/manage/account/two-factor/
- https://pypi.org/manage/account/two-factor/

Use an authenticator app (Authy, 1Password, Google Authenticator). Save the recovery codes somewhere safe.

### 4. Create API tokens (one per account)

Tokens are how `twine` authenticates — never use your password.

**TestPyPI:**
1. Go to https://test.pypi.org/manage/account/token/
2. "Add API token" → name it `app-classifier-upload` → scope: "Entire account" (you'll narrow scope after first upload)
3. **Copy the token immediately** — starts with `pypi-`. You CANNOT see it again.

**PyPI:**
1. Go to https://pypi.org/manage/account/token/
2. Same flow.

### 5. Store tokens in `~/.pypirc`

Create or edit `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
repository = https://upload.pypi.org/legacy/
username = __token__
password = pypi-AgEIcHlwa…<your real PyPI token>

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-AgENd…<your real TestPyPI token>
```

Then lock it down:

```bash
chmod 600 ~/.pypirc
```

**Username is literally the string `__token__`** — not your account name. The password is the token starting with `pypi-`.

### 6. Update repository URLs in `pyproject.toml`

Open `oss/app-classifier/pyproject.toml` and replace the placeholders:

```toml
[project.urls]
Homepage = "https://github.com/YOUR-USERNAME/app-classifier"
Issues = "https://github.com/YOUR-USERNAME/app-classifier/issues"
Source = "https://github.com/YOUR-USERNAME/app-classifier"
```

Replace `YOUR-USERNAME` with your real GitHub username or org (`repolens`, `codefixer`, etc.).

### 7. Install build tools

```bash
pip install --upgrade build twine
```

- `build` packages your code into a wheel
- `twine` uploads the wheel to PyPI

---

## Releasing v0.1.0 (your first release)

### Step 1 — Verify the package builds cleanly

```bash
cd /Users/kadaba/Documents/AI_Scanner/Codefixer/oss/app-classifier

# Make sure all tests pass
pytest -q
# Expected: 33 passed
```

### Step 2 — Build the distributable artifacts

```bash
# Clean any previous builds
rm -rf dist/ build/ src/*.egg-info

# Build wheel + source distribution
python -m build
```

Expected output: `dist/app_classifier-0.1.0-py3-none-any.whl` and `dist/app_classifier-0.1.0.tar.gz`.

### Step 3 — Validate the metadata

```bash
twine check dist/*
```

Expected: `Checking dist/app_classifier-0.1.0-py3-none-any.whl: PASSED`. If anything fails, fix it before uploading — PyPI is strict about README rendering.

### Step 4 — Upload to TestPyPI first (dry run)

```bash
twine upload --repository testpypi dist/*
```

Expected output:
```
Uploading distributions to https://test.pypi.org/legacy/
Uploading app_classifier-0.1.0-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ...
View at: https://test.pypi.org/project/app-classifier/0.1.0/
```

Open that URL — does the README render correctly? Does the version look right? Are the classifiers + topics visible?

### Step 5 — Test the install from TestPyPI

In a fresh virtualenv (CRITICAL — don't pollute your dev env):

```bash
# Make a throwaway venv
python -m venv /tmp/test-install
source /tmp/test-install/bin/activate

# Install from TestPyPI (need extra-index because our package may have
# regular pypi-hosted deps, though it doesn't currently)
pip install --index-url https://test.pypi.org/simple/ app-classifier

# Smoke test
app-classifier --version
# Expected: app-classifier 0.1.0

app-classifier /path/to/some/repo
# Expected: full classification output
```

If anything is broken (missing data files, import errors, etc.) — fix it, **bump version to `0.1.1`** in `pyproject.toml`, repeat from Step 2. You cannot re-upload `0.1.0`.

### Step 6 — Upload to real PyPI

Once TestPyPI works perfectly:

```bash
deactivate  # leave the throwaway venv if you're still in it
cd /Users/kadaba/Documents/AI_Scanner/Codefixer/oss/app-classifier

twine upload dist/*
```

You'll be prompted for your 2FA code. Approve it.

Expected output:
```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading app_classifier-0.1.0-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ...
View at: https://pypi.org/project/app-classifier/0.1.0/
```

### Step 7 — Verify production install works

In another fresh venv:

```bash
python -m venv /tmp/test-real
source /tmp/test-real/bin/activate
pip install app-classifier
app-classifier --version
deactivate
```

**Congratulations — you're shipped.** `pip install app-classifier` now works for anyone in the world.

### Step 8 — Tag the release in git

```bash
cd /Users/kadaba/Documents/AI_Scanner/Codefixer/oss/app-classifier
git add -A
git commit -m "Release v0.1.0"
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

### Step 9 — Create a GitHub release

```bash
# Using GitHub CLI
gh release create v0.1.0 \
  --title "v0.1.0 — Initial release" \
  --notes-file CHANGELOG.md \
  dist/*.whl dist/*.tar.gz
```

Or via the web UI: https://github.com/YOUR-USERNAME/app-classifier/releases/new

Attach the `.whl` and `.tar.gz` from `dist/` so users without `pip` can download directly.

### Step 10 — Lock down the API token

Now that the project exists, you can scope the token tighter:

1. Go to https://pypi.org/manage/account/token/
2. Revoke the broad token you created earlier
3. Create a new token scoped to **just the `app-classifier` project**
4. Update `~/.pypirc` with the new token

This way, if `~/.pypirc` ever leaks, the blast radius is one project, not your whole account.

---

## Releasing v0.2.0 and beyond (every release after the first)

The fast path. Once the first release is done, releases compress to ~3 minutes:

```bash
cd oss/app-classifier

# 1. Bump version in pyproject.toml + CHANGELOG.md
sed -i '' 's/version = "0.1.0"/version = "0.2.0"/' pyproject.toml
# Edit CHANGELOG.md to add the v0.2.0 entry

# 2. Test
pytest -q

# 3. Build
rm -rf dist/ build/ src/*.egg-info
python -m build

# 4. Upload
twine check dist/*
twine upload dist/*

# 5. Tag
git add pyproject.toml CHANGELOG.md
git commit -m "Release v0.2.0"
git tag v0.2.0
git push origin main v0.2.0

# 6. GitHub release
gh release create v0.2.0 --title "v0.2.0" --notes-file CHANGELOG.md dist/*
```

---

## Alternative: GitHub Actions auto-publish (recommended for ongoing maintenance)

After your first manual release, automate future ones with **PyPI Trusted Publishing** (OIDC — no API tokens stored anywhere).

### Step 1 — Configure trusted publisher on PyPI

1. Go to https://pypi.org/manage/project/app-classifier/settings/publishing/
2. Add a publisher:
   - PyPI Project Name: `app-classifier`
   - Owner: `YOUR-GITHUB-USERNAME`
   - Repository name: `app-classifier`
   - Workflow name: `publish.yml`
   - Environment name: `pypi` (we'll create this in step 3)

### Step 2 — Add the workflow

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/project/app-classifier/
    permissions:
      id-token: write  # required for trusted publishing

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Step 3 — Create the `pypi` environment

1. GitHub repo → Settings → Environments → New environment → name: `pypi`
2. (Optional) Add a required reviewer so releases need manual approval

### Step 4 — Future releases are one click

Now to release:

1. Bump version in `pyproject.toml` + update `CHANGELOG.md`
2. Commit + push to `main`
3. Go to GitHub → Releases → Draft a new release → tag `v0.2.0` → Publish
4. The workflow auto-builds + publishes to PyPI

No tokens, no `~/.pypirc`, no laptop dependency. The release is reproducible from CI.

---

## Common gotchas

### "HTTPError: 403 Forbidden" on upload

- Check `username` in `.pypirc` is the literal string `__token__` (not your account name)
- Check the token isn't expired
- Check 2FA is enabled on the account

### "HTTPError: 400 Bad Request — File already exists"

You're trying to re-upload a version that's already there. **PyPI is immutable.** Bump the version in `pyproject.toml` and rebuild.

### "InvalidDistribution: README content is invalid"

The README has Markdown that PyPI's renderer can't parse. Most common cause: HTML tags like `<details>`. `twine check dist/*` will tell you exactly what's wrong. Fix in README.md, rebuild.

### Package install fails with "ModuleNotFoundError: No module named 'app_classifier.data'"

The bundled JSON file isn't being shipped. Verify in `pyproject.toml`:

```toml
[tool.setuptools.package-data]
app_classifier = ["data/*.json"]
```

And rebuild.

### `pip install` finds an old version

PyPI's CDN sometimes caches for 1-5 minutes after upload. Wait, retry, or force:

```bash
pip install --no-cache-dir --upgrade app-classifier
```

### Name was taken by a squatter

You have three options:
1. Pick a different name (e.g., `repolens`)
2. Suffix the existing name (`app-classifier-toolkit`)
3. Email PyPI moderation at admin@pypi.org with proof your name is more legitimate (rarely works for generic names)

### "Project description content type is required"

Add this to `pyproject.toml` under `[project]`:

```toml
readme = "README.md"
```

(Already set in your `pyproject.toml`.)

---

## Versioning policy (recommended)

Follow [SemVer](https://semver.org/):

- **Patch (0.1.0 → 0.1.1)** — bug fixes, no behavior change
- **Minor (0.1.0 → 0.2.0)** — new features, backwards compatible (e.g., add a new fingerprint, add a CLI flag)
- **Major (0.x.0 → 1.0.0)** — breaking changes (e.g., rename `AppDescription.app_category`, remove a function from the public API)

Stay on `0.x.y` until the API is genuinely stable. `1.0.0` is a public commitment to maintain backwards compatibility on the documented API.

---

## TL;DR — the 9 commands you actually need

For the first release:

```bash
cd oss/app-classifier
pytest -q                                           # 33 passed
rm -rf dist/ build/ src/*.egg-info && python -m build
twine check dist/*
twine upload --repository testpypi dist/*           # dry run
# verify on https://test.pypi.org/project/app-classifier/
twine upload dist/*                                 # real upload
git tag v0.1.0 && git push origin v0.1.0
gh release create v0.1.0 --title "v0.1.0" --notes-file CHANGELOG.md dist/*
```

Done. `pip install app-classifier` now works globally.
