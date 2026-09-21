# Chapter 12 companion files

| File | Listing | What it is |
|---|---|---|
| `audit_logger.py` | 12.1 | Hash-chained audit records over an append-only store |
| `append_only_store.py` | ships with 12.1 | Local filesystem (`O_EXCL`) and S3 Object Lock backends |
| `verify_chain.py` | **Exercise 12.1** | Reference solution. Deliberately not in the chapter text. |
| `data_custody.py` | 12.2 | What each decision touched, who could read it, when it is destroyed |
| `audit_queries.py` | 12.3 | Dossier assembly across chain + custody + verification |

## `verify_chain` is an exercise

Chain verification is Exercise 12.1. It is not a method on `AuditLogger`
and it is not reproduced in the chapter body; this file exists so a
reader can check their own answer. If you are editing the manuscript,
that separation is load-bearing: printing the solution next to the
exercise removes the exercise.

## Required S3 bucket configuration

`S3ObjectLockStore` only delivers what Chapter 12 claims if the bucket is
configured for it. Object Lock **cannot be enabled on an existing
bucket** through the console, so this has to be right at creation time.

1. **Create the bucket with Object Lock enabled.** This requires
   versioning, which S3 turns on with it. Object Lock cannot be added
   later without AWS Support involvement.

   ```bash
   aws s3api create-bucket \
     --bucket acme-ai-audit \
     --region us-east-1 \
     --object-lock-enabled-for-bucket
   ```

2. **Set a default retention in COMPLIANCE mode.** The store passes
   per-object retention too, but a bucket default means an object written
   by some other path is still protected.

   ```bash
   aws s3api put-object-lock-configuration \
     --bucket acme-ai-audit \
     --object-lock-configuration '{
       "ObjectLockEnabled": "Enabled",
       "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 2555}}
     }'
   ```

   **COMPLIANCE, not GOVERNANCE.** In GOVERNANCE mode a principal with
   `s3:BypassGovernanceRetention` can delete the object, which is the
   exact claim the audit chain is making. `S3ObjectLockStore` raises on
   construction if you pass GOVERNANCE, because that configuration makes
   the chapter's argument false rather than merely weaker.

3. **Pick `retention_days` from the obligation, not from storage cost.**
   In COMPLIANCE mode the retention cannot be shortened afterwards by
   anyone, including the account root. Seven years (2555 days) is the
   default here because it is a common financial-services floor; yours
   comes from your own regime.

4. **Block public access and encrypt at rest.**

   ```bash
   aws s3api put-public-access-block \
     --bucket acme-ai-audit \
     --public-access-block-configuration \
       "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

   aws s3api put-bucket-encryption \
     --bucket acme-ai-audit \
     --server-side-encryption-configuration \
       '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'
   ```

5. **Deny `s3:PutObjectRetention` to the writer role.** The application
   should be able to write records and extend nothing. Without this a
   compromised application credential can set a one-day retention on
   everything it writes.

6. **Budget for it.** Locked objects cannot be deleted before expiry, so
   lifecycle rules will not clear them and storage cost grows
   monotonically for the whole retention window. This surprises people in
   year two, not year one.

## Running the local backend

`LocalFilesystemStore` uses `O_CREAT | O_EXCL`, so a duplicate key raises
`DuplicateKeyError` and the check-and-create is a single syscall. It is
honest about its limits: root can still delete the file, so it is a
development and CI backend, not an evidentiary one.
