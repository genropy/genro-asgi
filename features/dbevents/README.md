# Table subscriptions and dbevents

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

A page subscribes to tables; a database event is delivered to the
subscribed pages through the `DeliveryDesk`: subscriptions, pending
mailboxes for pages between two homes, age-bounded events.

Interactions: datachanges (same desk) · orchestration (mobility must not lose a pending event).

## The delivery

```mermaid
flowchart LR
    E["db event on a table"] -->|up the lane| C[SpaCommander]
    C --> D["DeliveryDesk
    table subscriptions · pending mailboxes · age-bounded events"]
    D -->|ADDRESSED to the subscribed pages| T["their workers"]
    T -->|interim: ping/collect pull| B[browser]
```

A page between two homes does not lose its events: they wait in the pending
mailbox, bounded by age.
