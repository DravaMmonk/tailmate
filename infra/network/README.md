# Network Boundary

This directory documents the private connectivity boundary for the application.
This file is a controlled infrastructure document and must be updated in the same Pull Request as any connectivity boundary change.

Rules:

- private backends must be reached through a Private Service Connect network attachment
- the PSC network attachment subnet must use routable RFC 1918 address space, and Google recommends a `/28` subnet for Vertex AI PSC interfaces
- the Vertex AI service agent must have `roles/compute.networkAdmin` in the network attachment project
- Shared VPC deployments must additionally grant the Vertex AI service agent `roles/compute.networkUser` in the host project
- DNS peering settings must remain aligned with the network attachment contract when custom domains are used
- private DNS peering requires the Vertex AI service agent to hold `roles/dns.peer`
- application code must not depend on public ingress to internal systems
