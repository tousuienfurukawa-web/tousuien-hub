name: Validate Order CSV

on:
  workflow_dispatch: {}
  pull_request:
    paths:
      - 'dist/受注登録.csv'
      - 'validate_order_csv.py'

permissions:
  contents: read
  issues: write
  pull-requests: write

jobs:
  validate:
    name: Run CSV validation
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Upgrade pip
        run: python -m pip install --upgrade pip

      - name: Run validation
        id: run_validation
        continue-on-error: true
        run: |
          # Exit immediately on unbound variable, but do not exit on non-zero commands
          set -uo pipefail

          # Ensure target CSV exists
          if [ ! -f dist/受注登録.csv ]; then
            echo "ERROR: dist/受注登録.csv not found" > validation_summary.txt
            echo "VALIDATION_FAILED=true" >> $GITHUB_ENV
            exit 0
          fi

          # Run the validator and capture output; set env var if exit code != 0
          python validate_order_csv.py dist/受注登録.csv > validation_summary.txt 2>&1
          rc=$? || rc=$?
          if [ "$rc" -ne 0 ]; then
            echo "VALIDATION_FAILED=true" >> $GITHUB_ENV
          fi

      - name: Upload validation summary (artifact)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: validation-summary
          path: validation_summary.txt

      - name: Post validation summary as PR comment
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v6
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const fs = require('fs');
            const path = 'validation_summary.txt';
            let summary = 'No validation_summary.txt found.';
            if (fs.existsSync(path)) {
              summary = fs.readFileSync(path, 'utf8');
            }
            const body = `### 自動検証サマリ\n\n\`\`\`\n${summary}\n\`\`\``;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body
            });

      - name: Fail if validation failed
        if: always()
        run: |
          if [ "${VALIDATION_FAILED:-}" = "true" ]; then
            echo "Validation failed. See validation_summary.txt artifact or PR comment for details."
            exit 1
          else
            echo "Validation passed."
          fi
