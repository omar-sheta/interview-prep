# Development Guide

Use the cleanup clone for refactors and keep the live Spark service checkout
separate.

## Backend

```bash
/home/omar/miniforge3/envs/interview/bin/python -m pytest server/tests
```

The service environment is the `interview` conda environment. Avoid relying on
the base conda Python because it may have a different Python version and missing
test dependencies.

## Frontend

```bash
cd client
npm run build
npm run lint
```

`npm run lint` is useful for cleanup work, but existing React hook lint rules may
surface non-runtime cleanup items.

## Live Service Safety

Do not restart or deploy from cleanup branches. The live user service runs from
the production checkout and should only be restarted intentionally from that
checkout.
