# LegacyPilot Source Workspace

This directory is reserved for repositories and artifacts that LegacyPilot analyzes at runtime.

Suggested layout:

```text
source/
  repos/      cloned or mounted repositories to analyze
  uploads/    uploaded repository archives
  analysis/   generated graph snapshots or exported analysis artifacts
```

Do not put Spring Boot configuration YAML files here. Maven/Spring Boot configuration belongs in `src/main/resources`.
