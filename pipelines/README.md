# Pipelines

Cotal Lang programs for the repeated parts of the flow. See `docs/cotal-lang.md` for what runs where and why nothing here can be started on the current mesh yet.

Validate a program offline:

```
node -e 'const l=require("/opt/homebrew/lib/node_modules/cotal-ai/node_modules/@cotal-ai/lang");const v=l.validate(require("fs").readFileSync(process.argv[1],"utf8"));console.log(v.problems?.length ?? 0, "problems")' pipelines/review-and-merge.cotal.js
```
