# Project design: dynamic application bundles distributed through S3

**Version**: 0.1  
**Last Updated**: 2026-08-20  
**Status**: 🔴 DA REVISIONARE  
**Code reference**: `genro-asgi` `main` at `ef2229d`  
**Scope**: new core (`spa/orchestration/` and `applications/spa_app_new.py`)

## 1. Purpose

This document defines a distribution model in which:

- one Genro Framework container image is distributed unchanged to every customer;
- each customer application is delivered separately as a versioned bundle;
- application bundles are built by the application's own repository and CI;
- bundles are archived in S3 under explicit, meaningful and immutable names;
- groups can be added, replaced and removed while the server remains alive;
- users can be assigned explicitly to a group for iterative acceptance testing,
  canary releases or a full promotion;
- every application worker uses the same worker Python runtime, while the
  framework control plane may use a different Python version.

The primary use case is not only a conventional blue/green deployment. It is
the more general case in which a customer asks for a change, selected users
test repeated revisions, and the accepted revision may later become a normal
release without being rebuilt.

## 2. Status of this proposal

The architectural directions in section 3 were consolidated during the design
discussion. They are recorded here for review, not yet treated as implemented
or as normative repository specification.

The exact bundle format, the handling of resident user state during a group
refresh and the public lifecycle API still require explicit decisions. They are
listed in section 17 in the order in which they should be discussed.

No source-code change is authorized by this document.

## 3. Consolidated decisions

### 3.1 Framework distribution

- `genro-asgi` and its framework-owned dependencies form one platform release.
- The framework is not upgraded incrementally by customer, group or user.
- A framework update is a coordinated update of the whole installation.
- The framework container image is identical for all customers.

### 3.2 Application distribution

- Every application has its own repository and CI pipeline.
- The application repository is the release authority for its bundle.
- One bundle represents one exact build of the application and all
  application-owned dependencies needed by that build.
- Dependencies coming from other repositories are pinned to exact commits by
  the application build input; branch names alone are not sufficient.
- A physical bundle is immutable.
- A logical name such as `collaudo-fatture` may point to successive physical
  builds.

### 3.3 S3 model

- S3 is the preferred distribution store.
- Application versions use explicit object prefixes with meaningful names.
- S3 `VersionId` is not the primary business identifier of a bundle.
- S3 Versioning should remain enabled as protection against accidental
  overwrites and deletion, especially for mutable channel documents.
- A channel document may point `produzione`, `collaudo` or another logical name
  to one immutable bundle.

### 3.4 Runtime model

- Groups are dynamic runtime objects, not container images.
- A group may be added, refreshed or removed without restarting the server.
- Adding a group and assigning users to it are separate operations.
- A live group is pinned to a resolved immutable bundle, never to a mutable
  channel alone.
- Updating a logical group creates a new internal generation; files used by a
  running worker are never modified in place.

### 3.5 Python runtimes

- The control plane and the application workers may use different Python
  versions.
- All application workers in one platform installation use the same worker
  Python version and ABI.
- Changing the worker Python is a platform operation and requires rebuilding or
  revalidating every application bundle.
- Changing only the control-plane Python does not require rebuilding bundles if
  the worker protocol remains compatible.

## 4. Terminology

**Platform image**  
The container image distributed identically to all customers. It contains the
control runtime, the worker runtime and the framework-owned operating-system and
Python dependencies.

**Control runtime**  
The Python environment that runs the ASGI server, commander, group lifecycle,
bundle resolution and cache management.

**Worker runtime**  
The common Python environment that starts application worker processes and
implements their protocol with the commander.

**Bundle**  
One immutable application artifact produced by CI. It contains the application
and its application-owned dependencies, but not the control runtime.

**Bundle name**  
A meaningful logical family, for example `collaudo-fatture`.

**Build identifier**  
The immutable revision within a bundle family, for example `004` or
`2026.08.20-01`.

**Channel**  
A mutable reference such as `produzione` or `collaudo` that points to an
immutable bundle.

**Group**  
A runtime placement and policy boundary whose workers all execute the same
resolved bundle.

**Generation**  
An internal incarnation of a logical group. Refreshing `collaudo-fatture`
replaces generation N with generation N+1 while keeping the user-facing group
name stable.

**Cohort**  
The users deliberately assigned to a group, for example Mario and Luigi during
customer acceptance testing.

## 5. Target architecture

```text
Application repositories                     S3 bundle store
and their CI pipelines                     explicit immutable builds
          |                                           |
          | build, test, publish                      | resolve and download
          v                                           v
+------------------------------------------------------------------------+
|                    Genro Framework container                           |
|                                                                        |
|  Control runtime (Python A)                                            |
|  +------------------------------------------------------------------+  |
|  | ASGI server -> commander -> bundle catalog/cache -> group lifecycle| |
|  +------------------------------------------------------------------+  |
|                                  |                                     |
|                                  | spawn                               |
|                                  v                                     |
|  Worker runtime (Python B, common to every bundle)                     |
|      +-------------------+   +-------------------+                      |
|      | production worker |   | acceptance worker |                     |
|      | bundle build 017  |   | bundle build 004  |                     |
|      +-------------------+   +-------------------+                      |
+------------------------------------------------------------------------+
```

The control plane never imports customer application modules. Each worker is a
separate process, selects exactly one extracted bundle and imports application
code only after its bundle path has been installed for that process.

Commander and workers communicate through the existing socket and serialized
frame protocol. They do not share a Python interpreter, application objects or
process memory.

## 6. Platform image

The proposed image contains two explicit environments.

```text
/opt/genro/control/
    Python A
    genro-asgi control plane
    control-plane dependencies

/opt/genro/worker/
    Python B
    worker entry point
    worker protocol and lifecycle
    framework-owned worker dependencies

/var/cache/genro/bundles/
    immutable extracted application bundles
```

Initially, the worker runtime may install the same `genro-asgi` distribution as
the control runtime, under Python B. This does not create independently
upgradable framework versions: both installations belong to the same platform
release and must be built together.

A future split into a smaller worker-runtime package is possible, but is not a
prerequisite and should not be introduced until measured need justifies it.

The platform image must publish a stable worker-runtime identity, for example:

```text
worker_runtime: genro-worker-P17
worker_python: cp312
worker_platform: linux-aarch64
worker_runtime_digest: sha256:...
```

Every accepted bundle must declare compatibility with this identity.

## 7. Ownership boundary between platform and bundle

A Python distribution must have one owner in a platform release.

Platform-owned components are identical for every customer and cannot be
overridden by a bundle. Application-owned components may vary between builds.

The working rule is:

> If a component may change for one customer or one group without upgrading
> every customer, it belongs to the application bundle rather than the common
> platform image.

This rule is especially important for GenroPy legacy and shared Genro packages.
Any component that a customer build is allowed to pin to a different commit
cannot simultaneously be imported from the common worker runtime.

The definitive ownership list is still an open decision. Bundle validation
must reject collisions with platform-owned distributions.

## 8. S3 organization

S3 folders are object-key prefixes. The proposed layout is:

```text
s3://genro-bundles/
  customers/
    acme/
      applications/
        fatture/
          bundles/
            collaudo-fatture/
              004/
                bundle.tar.zst
                manifest.json
                checksums.sha256
              005/
                bundle.tar.zst
                manifest.json
                checksums.sha256
            release-2026.08/
              001/
                bundle.tar.zst
                manifest.json
                checksums.sha256
          channels/
            produzione.json
            collaudo.json
```

Bundle prefixes are immutable. CI must fail if the intended bundle objects
already exist. S3 Versioning remains enabled but is a safety mechanism rather
than the normal way to select an application release.

A channel document is deliberately small:

```json
{
  "schema": 1,
  "customer": "acme",
  "application": "fatture",
  "channel": "collaudo",
  "bundle_name": "collaudo-fatture",
  "build": "005",
  "manifest_key": "customers/acme/applications/fatture/bundles/collaudo-fatture/005/manifest.json",
  "bundle_sha256": "..."
}
```

Channel updates should use an S3 conditional write against the previously read
object identity, so two publishers cannot silently overwrite one another's
decision.

## 9. Bundle manifest

The manifest is stored both beside the archive and inside it. The external copy
allows compatibility and authorization checks before downloading a potentially
large artifact.

Proposed minimum fields:

```yaml
schema: 1
customer: acme
application: fatture
bundle_name: collaudo-fatture
build: "005"

source:
  repository: ssh://git.example/acme/fatture
  tag: bundle/collaudo-fatture/005
  commit: 8ab31e...

worker_contract:
  python_abi: cp312
  platform: linux-aarch64
  runtime: genro-worker-P17

dependencies:
  uv_lock_sha256: ...
  repositories:
    genropy: 71ac9f...
    package_contabilita: c19d02...
    package_magazzino: f817bc...

entrypoint:
  worker_class: acme_fatture.worker:FattureWorker

artifact:
  format: genro-application-bundle-v1
  archive: bundle.tar.zst
  sha256: ...
  uncompressed_size: 123456789

created_at: 2026-08-20T10:00:00Z
```

The manifest must describe source identity, not only human-readable versions.
Every repository dependency therefore records an exact commit.

## 10. Proposed bundle contents

The first format should be deliberately small:

```text
bundle root/
├── manifest.json
├── application/
│   └── application repository content required at runtime
├── python/
│   └── application-owned Python distributions
└── assets/
    └── optional runtime assets
```

The bundle should not contain a conventional relocatable virtualenv. Virtualenv
scripts and interpreter references may contain build-machine paths. A safer
first experiment is to materialize application-owned distributions into a
plain target directory for the declared worker Python and platform.

UV currently supports installation into a target directory and selection of a
Python version and platform. The exact command line belongs to the CI prototype
and must be proven against packages with native extensions before ratification.

At worker start, the bootstrap adds the resolved bundle's `python/` and
`application/` directories to that process's import paths before importing the
declared worker class. It must reject any distribution that collides with the
platform ownership list.

## 11. Application repository and CI

### 11.1 Repository responsibility

The application repository contains:

- application source;
- `pyproject.toml` or equivalent dependency declaration;
- `uv.lock` pinning the complete application dependency graph;
- bundle build configuration;
- tests that qualify a bundle;
- the CI workflow that publishes to the application's S3 prefix.

The application lock must resolve other repositories to exact immutable
commits or immutable package artifacts.

### 11.2 Trigger model

The recommended trigger is an immutable source tag:

```text
bundle/<bundle-name>/<build>

bundle/collaudo-fatture/004
bundle/collaudo-fatture/005
bundle/release-2026.08/001
```

The logical name remains stable while the source tags progress. Git tags
should not be moved or recreated.

An optional manually dispatched CI build may use the same naming rules, but it
must still record the exact source commit and produce a new immutable build
identifier.

### 11.3 Pipeline

```text
1. Read and validate the source tag.
2. Verify that the lockfile is present and unchanged.
3. Build inside an image matching the target worker ABI and operating system.
4. Materialize application source and application-owned dependencies.
5. Run unit, integration and bundle-import tests.
6. Validate that no platform-owned distribution is present in the bundle.
7. Generate the manifest and checksums.
8. Create the deterministic archive.
9. Verify that the destination S3 prefix does not already exist.
10. Upload archive, manifest and checksum.
11. Read the objects back or validate their S3 checksums.
12. Emit the immutable bundle reference as the CI result.
```

Publishing a bundle and changing a channel are separate permissions and
separate CI operations. A successful build does not automatically promote
itself to production.

## 12. Runtime bundle resolution and cache

The control plane needs a component responsible for resolving, downloading and
verifying bundles. `BundleManager` is used here only as a descriptive role, not
as an approved public class name.

Input forms may be:

```text
explicit: customer/application/bundle-name/build
channel:  customer/application@collaudo
```

A channel is resolved once to an explicit manifest and checksum. The live group
records the resolved identity.

Proposed cache path:

```text
/var/cache/genro/bundles/<customer>/<application>/<sha256>/
```

Cache installation must be transactional:

```text
download to temporary path
    -> verify manifest and checksum
    -> extract to temporary directory
    -> validate structure and compatibility
    -> atomic rename to final digest path
```

Concurrent requests for the same digest must share one installation operation.
An incomplete download or failed verification must never become visible as a
usable cache entry.

The first implementation need not automatically reclaim cache space. It must
record which bundles are active; eviction policy can be introduced after real
growth has been measured.

## 13. Dynamic group lifecycle

### 13.1 Add a group

Conceptual operation:

```text
add group
  name: collaudo-fatture
  bundle: acme/fatture/collaudo-fatture/005
  policy: ...
```

Lifecycle:

```text
RESOLVING -> FETCHING -> VERIFYING -> WARMING -> ACTIVE
                                          \\-> FAILED
```

Steps:

1. Validate that the logical group name is not already active.
2. Resolve the bundle or channel to an immutable manifest.
3. Verify worker-runtime compatibility.
4. Ensure that the bundle is installed in the local cache.
5. Construct the group with the common worker executable and bundle identity.
6. Start one reception worker.
7. Wait for presentation and verify that it reports the expected bundle
   checksum and runtime identity.
8. Mark the group active.

The group receives no users merely because it exists.

### 13.2 Assign a cohort

User-to-group selection remains an application policy. Initial support may use
an explicit user list. Percentage selection, tenant rules and feature flags are
not required for the first proof.

Once assigned, a user remains on the selected group. The front continues to be
stateless and does not choose the group on each request.

### 13.3 Refresh a group

Refreshing a logical name must not change files under running processes.

```text
collaudo-fatture generation 3 -> build 004
collaudo-fatture generation 4 -> build 005
```

Proposed sequence:

1. Resolve and install the new build.
2. Create generation 4 without accepting traffic.
3. Warm a worker and verify its presentation.
4. Stop new placements on generation 3.
5. Apply the chosen resident-user transition policy.
6. Make generation 4 current for the logical group.
7. Stop generation 3.
8. Retain its cache entry for rollback.

Whether resident users restart cleanly or carry a frozen parcel across
generations is deliberately unresolved. Iterative acceptance testing should
prefer a clean restart until parcel compatibility has an explicit contract.

### 13.4 Remove a group

```text
ACTIVE -> DRAINING -> EMPTY -> REMOVED
```

Removal first prevents new assignments. It must then follow an explicit policy
for resident users: refuse while non-empty, restart them on another group, or
wait for natural departure. Silent cross-version fallback is not allowed.

After the group is empty, its workers are stopped and every commander index is
checked before the group is removed from the map.

### 13.5 Promote and roll back

Promotion changes a reference or group policy; it does not rebuild an artifact.
The exact bundle tested by the cohort becomes the production bundle.

Rollback resolves to a previously installed immutable bundle, warms a new
generation and applies the same controlled switch used by refresh.

## 14. Compatibility and isolation

### 14.1 Runtime identity

Before becoming active, a worker must present:

- logical group and internal generation;
- bundle checksum;
- bundle name and build;
- worker Python version and ABI;
- worker-runtime identity;
- process identity.

The current presentation contains the spawn configuration and process id, but
does not yet express this complete compatibility contract.

### 14.2 Environment isolation

The current `WorkerHandler.launch_process()` copies the complete control-plane
environment before spawning the child. A worker launched under another Python
runtime could therefore inherit `PYTHONPATH`, virtualenv or application-related
variables from the control process.

The bundle design requires a deliberate worker environment:

- preserve only approved operating and service variables;
- set the spawn payload;
- identify the resolved bundle path;
- avoid inherited Python paths from the control runtime;
- install bundle import paths inside the worker bootstrap;
- never import customer code in the commander process.

### 14.3 Native dependencies

Any compiled Python extension in a bundle must match the worker Python ABI,
operating system and architecture declared by the platform. CI must build in a
compatible builder image and must not rely on libraries absent from the runtime
container.

## 15. Relationship with the current code

The current new core already provides several required foundations.

| Capability | Current state |
|---|---|
| Per-group interpreter | Present through `executable` |
| Per-group entry module and worker class | Present |
| Group registration in the commander | Present during construction |
| Start and stop worker processes | Present |
| Sticky user-to-group record | Present |
| Default group for newcomers | Present at startup |
| Dynamic public add/remove lifecycle | Missing |
| Bundle reference and S3 resolution | Missing |
| Transactional local bundle cache | Missing |
| Bundle path installation in worker | Missing |
| Sanitized cross-runtime child environment | Missing |
| Group generation and live replacement | Missing |
| Public cohort assignment operation | Missing |
| Public default-group promotion operation | Missing |
| Bundle/runtime identity in presentation | Missing |

`SpaCommander.start()` currently starts only the default group's reception.
Other groups can exist, but the current code does not expose the complete live
creation, warming and retirement transaction required by this project.

The new core also does not yet contain the complete GenroPy data plane. Bundle
work can begin with a diagnostic worker and synthetic application, but a real
customer pilot depends on the relevant Macro 5 and Macro 6 work.

## 16. Validation plan

### Phase B0 - Bundle format experiment

- Build two bundles from a minimal application repository.
- Give both bundles the same module names but different observable versions.
- Materialize dependencies for the common worker Python.
- Prove that neither bundle contains or overrides platform-owned packages.
- Verify deterministic manifest and archive checksums.

**Gate:** both bundles import independently under the worker runtime and fail
under an incompatible Python ABI.

### Phase B1 - Local dual-runtime proof

- Run the commander under control Python A.
- Spawn workers under worker Python B.
- Load two different application bundles in simultaneous worker processes.
- Verify that no control-runtime Python path leaks into a worker.

**Gate:** the two bundles coexist and each response reports the expected bundle
checksum, Python identity and process identity.

### Phase B2 - S3 publication and cache

- Publish explicit immutable bundle prefixes from CI.
- Resolve an explicit build and a channel document.
- Download, verify and atomically install the bundle.
- Exercise corrupted archive, wrong checksum, absent object, incompatible ABI
  and concurrent download cases.

**Gate:** only a fully verified digest path can become visible to a group.

### Phase B3 - Live group creation and removal

- Start the server with production traffic.
- Add an empty acceptance group without restarting the server.
- Warm its first worker and verify readiness.
- Assign two named users and confirm sticky routing.
- Drain and remove the group while production remains available.

**Gate:** control-plane availability and production users are unaffected by the
whole operation.

### Phase B4 - Iterative acceptance refresh

- Publish three builds under one logical acceptance name.
- Refresh the group from build 1 to 2 to 3.
- Verify that no group ever contains workers from two physical builds.
- Inject a broken build and prove that the old generation remains active.
- Roll back to the previous verified build.

**Gate:** the logical name remains stable while every live generation is pinned
to one immutable checksum.

### Phase B5 - Promotion

- Promote the exact accepted bundle to production without rebuilding it.
- Verify explicit handling of users resident on the previous production build.
- Verify rollback to the previous production bundle.

**Gate:** the checksum promoted is identical to the checksum tested by the
acceptance cohort.

### Phase B6 - Operational pilot

- Use a non-critical customer copy.
- Measure bundle size, download time, extraction time, worker warm-up time and
  cache growth.
- Exercise IAM denial, temporary S3 unavailability and server restart with a
  warm cache.

**Gate:** measured behaviour supports the final cache, timeout and retention
policies.

## 17. Security and operations

Minimum controls:

- CI has write access only to its customer/application S3 prefix.
- Runtime containers have read-only access to bundle objects.
- Channel promotion uses a distinct permission from bundle publication.
- Server-side encryption and transport encryption are enabled.
- Archive paths are validated during extraction to prevent path traversal.
- Bundle size and extracted size are checked against declared limits.
- SHA-256 is verified before activation.
- Every add, refresh, assignment, promotion, rollback and removal is recorded
  with actor, logical group, bundle identity and outcome.

Artifact signing and a software bill of materials are valuable later controls,
but are not required for the first functional proof unless deployment crosses
an untrusted administrative boundary.

## 18. Acceptance criteria for the project

The project is successful when all of the following are true:

1. One unchanged framework image can serve different customer bundles.
2. Control plane and workers can run supported different Python versions.
3. All workers share one declared worker Python and runtime identity.
4. An application CI can publish a reproducible immutable bundle to S3.
5. Every bundle identifies the exact commits of all included repositories.
6. A group can be added and warmed without restarting the server.
7. Explicit users can be assigned to the group and remain sticky to it.
8. A logical group can move to a new physical build without mixing builds.
9. A failed replacement leaves the old generation usable.
10. A group can be drained and removed without disturbing other groups.
11. The tested bundle can be promoted without rebuilding it.
12. Rollback selects an earlier immutable bundle and is observable.
13. Platform-owned packages cannot be overridden by a bundle.
14. S3 or cache failures cannot expose a partial bundle to a worker.

## 19. Decisions still required

These decisions should be taken one at a time.

### D1 - Bundle Python layout

Choose the concrete representation of application-owned Python distributions.

- plain target directory materialized by UV;
- wheel set expanded by the runtime;
- another proven relocatable format.

**Initial recommendation:** plain target directory, validated with native
extensions before adoption.

### D2 - Platform ownership list

Define exactly which distributions belong to the common worker runtime and
which may be supplied by customer bundles. GenroPy legacy is the first boundary
that must be classified.

### D3 - User state on acceptance refresh

Choose whether users receive a clean application restart, retain compatible
state, or follow a policy declared by the bundle pair.

**Initial recommendation:** clean restart for iterative acceptance builds;
cross-generation state only after a parcel compatibility contract exists.

### D4 - Source of cohort assignments

Choose where explicit assignments such as Mario and Luigi are administered and
persisted: application preferences, an administrative surface or another
existing service.

### D5 - Channel authority

Choose whether `produzione.json` and `collaudo.json` in S3 are authoritative or
whether S3 stores only artifacts while active references live in application
configuration.

### D6 - Cache retention

Choose how long inactive bundles remain available for rollback after real size
and growth measurements exist.

### D7 - Bundle authenticity

Decide when checksum verification is sufficient and when CI signatures become
mandatory.

## 20. Proposed implementation sequence

No implementation should begin before D1-D5 are decided.

```text
1. Ratify bundle and ownership contracts.
2. Build one standalone application CI prototype.
3. Prove dual Python runtimes locally with two diagnostic bundles.
4. Implement S3 resolution and transactional cache.
5. Add dynamic group lifecycle around existing GroupHandler/WorkerHandler.
6. Add explicit cohort administration.
7. Implement generation refresh, promotion and rollback.
8. Add operational controls and run a non-critical pilot.
```

The design intentionally does not introduce a generic deployment orchestrator,
a package installer inside the commander or one container image per application
release. UV belongs to CI; S3 distributes immutable artifacts; the live server
only resolves, verifies, caches and runs them.
