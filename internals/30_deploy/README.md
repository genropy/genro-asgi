# 30_deploy — shipping, updating, scaling

**Version**: 0.1 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

**Everything in this world is an unratified proposal.** Nothing here has been
settled by the owner, and no entry in it may be cited as a decision: read these
three as the shape of a conversation, not as a destination.

Their common subject is how an installation ships, updates and grows beyond one
machine, standing on the orchestration of [20_spa](../20_spa/README.md). The line they
share is that the commander stays the only owner of applicative policy — how many
workers, who lives where, which build gets traffic — whatever runtime executes
the containers underneath.

| Entry | In one line |
|---|---|
| [010 deployment-bundles](010_deployment-bundles/README.md) | immutable bundles on S3, channels, cohorts, promotion without rebuild |
| [020 kubernetes-deploy](020_kubernetes-deploy/README.md) | the cluster runs, the commander decides |
| [030 subcommanders](030_subcommanders/README.md) | delegated authority: root → subcommander → group → worker |
