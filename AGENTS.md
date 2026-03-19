# AGENTS.md

## Running the playbook

### Limiting to a specific server

When a server has supplementary `-deps` hosts (for dedicated Valkey, Postgres, etc.), use the **group name** instead of the individual host name to include all related hosts:

```bash
# WRONG — misses -deps hosts, services will fail to start due to missing dependencies (e.g. valkey)
just install-all --limit mash.met.surf

# CORRECT — includes the main host and all its -deps hosts
just install-all --limit mash_met_surf
```

Group names use underscores (`mash_met_surf`), not dots (`mash.met.surf`). They are defined in `inventory/hosts` as `[mash_met_surf]` sections containing the main host and its `-deps` entries.
