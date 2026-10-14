# Google Cloud private staging — dhruva-511613

Cloud Run serves the compiled UI/API, Cloud SQL holds a **separate test copy** of PostgreSQL, and a private Cloud Storage bucket retains source workbooks. Cloud Run's built-in Identity-Aware Proxy requires Google sign-in. Access defaults to the signed-in deploying account; additional named testers can be supplied. No public anonymous inventory endpoint is enabled. Cloud Run runs as a dedicated service account; SQL passwords stay in Secret Manager, and no service-account key is created.

The selected region is Mumbai, `asia-south1`. The test database uses PostgreSQL 16, a single-zone `db-f1-micro` instance and 10GB initial storage. Cloud Run uses 2 CPUs/2GiB with at most one instance. **Cloud SQL incurs ongoing charges even when Cloud Run scales to zero.** The script prints its resource plan before applying it. This configuration is for internal testing; production sizing, schema migration and resilience need a separate review.

## Run in your Cloud Shell

Clone the deployment source in Cloud Shell:

```bash
git clone --branch main https://github.com/dhruv407/dhruva.git
cd dhruva
python3 deploy/google-cloud.py --project dhruva-511613 --empty-data --apply
```

This starts a **blank test database**. Inventory exports, database backups and credentials are excluded from Git. Upload your original stock and master workbooks through **Data & imports** after Google sign-in. Previously saved snapshots and proposals are not restored by this source-only route. If the repository is private, use your normal GitHub authentication in Cloud Shell.

### Alternative: private backup bundle

This workspace has no authenticated Google Cloud account; a console project link does not grant access. Use the Cloud Shell terminal in your own project to run the prepared deployment bundle. Your account needs permission to enable services, create SQL/buckets/builds, manage the dedicated service accounts and their IAM bindings, access Secret Manager and deploy Cloud Run/IAP. Project billing must already be enabled.

Upload `rg-stock-google-cloud.tar.gz` into Cloud Shell using its file upload control. Then:

```bash
tar -xzf rg-stock-google-cloud.tar.gz
cd rg-stock-google-cloud
python3 deploy/google-cloud.py --project dhruva-511613
python3 deploy/google-cloud.py --project dhruva-511613 --apply
```

To grant additional testers, add `--testers owner@example.com,tester@example.com` to the apply command. Otherwise only your signed-in account is granted IAP access. Your Google organisation's OAuth/IAP policy may require an administrator to approve external tester accounts.

The bundle contains the app source, frozen dependency files, a database export and the two original workbooks. Keep it private and upload it only to your own Cloud Shell. Source/build ignore files prevent stock exports, database backups and local credentials from entering the container image or Cloud Build source upload.

The script creates a new staging database and restores the prepared source snapshot, rules and proposal history before starting the app. It never resets an existing SQL instance. If it fails after creating resources, retain the error and inspect those resources before retrying; the existing-instance guard prevents replaying an import or replacing credentials blindly. Deletion protection is enabled on SQL. Credentials are generated in memory, written briefly to a mode-600 temporary file for Secret Manager, then removed; they are never printed.

The private HTTPS service URL is printed only after deployment and IAP access configuration succeed. The Cloud Run filesystem itself is ephemeral; the source path is backed by the bucket through a Cloud Storage volume. PostgreSQL backups and source-object backups must be kept together.

## Test after Google sign-in

1. Open the printed URL with an allowed Google account. Confirm the **Private test workspace** banner; anonymous users must be sent to sign-in or denied access.
2. For a source-only deployment, confirm the empty dashboard marks branch inventory missing. Upload stock, validate and reconcile it, confirming cost, original age and HO usability; explicitly mark IK confirmed zero for the supplied baseline.
3. Import master rules into a draft. Sales history is pending; demand/profit objectives must remain unavailable until their data and economics are configured.
4. Inspect original label ages and source snapshot/rule provenance. If deploying a private backup bundle instead, confirm its restored snapshots and proposals.
5. In this **isolated test database**, clone a rule, simulate and compare, then test approval/activation gates. Record test dispatch and receipt references separately; branch exchanges require both HO route legs. Testing changes do not update the original development database.

A built container and local acceptance checks are not evidence of a successful Google Cloud deployment. Cloud SQL provisioning, Cloud Build, Secret Manager, bucket mounting, IAP sign-in and hosted browser checks remain unverified until the authenticated deployment executes.
