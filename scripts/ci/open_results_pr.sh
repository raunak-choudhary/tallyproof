#!/usr/bin/env bash
# After the weekly evaluation: put its results table in the README and open a pull
# request with the change. It never pushes to main; the pull request goes through the
# same checks and review as any other change.
#
# Needs GH_TOKEN in the llm-eval context: a fine-grained token for this repository
# only, with read and write access to contents and pull requests. Without it the
# step says so and stops, and the evaluation's reports are still kept as artifacts.
#
# DRY_RUN=1 renders the table and prints what would be pushed, without pushing.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
REPORT=$(ls -d var/eval/*/report.json 2>/dev/null | sort | tail -1 || true)
if [ -z "$REPORT" ]; then
  echo "No evaluation report found under var/eval; nothing to publish."
  exit 0
fi

# The README shows a run of every question, template and held-out; a smoke run,
# like the weekly one, is kept as an artifact but doesn't replace it.
if ! python3 -c 'import json, sys; sys.exit("held_out" not in json.load(open(sys.argv[1]))["by_set"])' "$REPORT"; then
  echo "$REPORT has no held-out questions; the README keeps the full run's table."
  exit 0
fi

# Refuses anything that isn't a quality run, so a placeholder never reaches the README.
if ! (cd backend && .venv/bin/python -m evals.readme_table "../$REPORT"); then
  echo "$REPORT is not a quality run; the README is left as it is."
  exit 0
fi
if git diff --quiet -- README.md; then
  echo "The results table is unchanged; no pull request needed."
  exit 0
fi

DAY=$(date -u +%Y-%m-%d)
BRANCH="eval/results-$DAY"
TITLE="docs: refresh the README results table ($DAY)"
BODY="The weekly evaluation finished as a quality run. This updates the results table in the README from \`$REPORT\`; the full reports are in the CircleCI job's artifacts."

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "Dry run: would push $BRANCH and open \"$TITLE\" with this change:"
  git --no-pager diff -- README.md
  git checkout -- README.md
  exit 0
fi
if [ -z "${GH_TOKEN:-}" ]; then
  echo "GH_TOKEN is not set in the llm-eval context, so no pull request was opened."
  exit 0
fi

REPO="${CIRCLE_PROJECT_USERNAME:?}/${CIRCLE_PROJECT_REPONAME:?}"
if [ "$BRANCH" = "main" ]; then
  echo "Refusing to push to main."
  exit 1
fi
git checkout -b "$BRANCH"
git -c user.name="Tallyproof weekly evaluation" -c user.email="weekly-eval@users.noreply.github.com" \
  commit --quiet -m "$TITLE" -- README.md
git push --quiet "https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git" "HEAD:refs/heads/$BRANCH"

payload=$(python3 -c 'import json, sys; print(json.dumps({"title": sys.argv[1], "head": sys.argv[2], "base": "main", "body": sys.argv[3]}))' \
  "$TITLE" "$BRANCH" "$BODY")
status=$(curl --silent --output /tmp/pr.json --write-out '%{http_code}' \
  -X POST "https://api.github.com/repos/${REPO}/pulls" \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -d "$payload")
if [ "$status" != "201" ]; then
  echo "GitHub refused the pull request (HTTP $status):"
  python3 -c 'import json; print(json.load(open("/tmp/pr.json")).get("message"))'
  exit 1
fi
python3 -c 'import json; print("Opened", json.load(open("/tmp/pr.json"))["html_url"])'
