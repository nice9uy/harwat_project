> **Superseded.** `prod.sh` now starts Garage with `--single-node --default-bucket`, which sets
> up the layout, the bucket and the app's access key on start from the key pair in `.env.prod`
> (the secret is not written to Garage's log). The manual steps below are only needed for a
> cluster of more than one node. See "Production data" in the README.

# Garage production cluster bootstrap

`prod.sh` starts the `garage` container but does **not** auto-configure its cluster layout,
bucket, or access key — that's deliberate (see the Podman infra design spec's Garage bootstrap
section: auto-generating production S3 credentials on every fresh `prod.sh` run would leak them
into container logs on first boot). Run these steps once, after `./prod.sh` has brought the stack
up for the first time.

Find the garage container name/id:

```bash
GARAGE=$(podman-compose --env-file "$(pwd)/.env.prod" -f podman/compose.yml -f podman/compose.prod.yml ps -q garage)
```

## 1. Assign and apply the single-node layout

```bash
podman exec -it "$GARAGE" /garage status
```

Copy the node ID shown, then:

```bash
podman exec -it "$GARAGE" /garage layout assign -z dc1 -c 1G <node-id>
podman exec -it "$GARAGE" /garage layout apply --version 1
```

## 2. Create the application bucket

```bash
podman exec -it "$GARAGE" /garage bucket create bmn-harwat-prod
```

## 3. Create an access key and grant it permissions

```bash
podman exec -it "$GARAGE" /garage key create bmn-harwat-app-key
podman exec -it "$GARAGE" /garage bucket allow \
  --read --write \
  bmn-harwat-prod \
  --key bmn-harwat-app-key
```

`garage key create`'s output includes the access key ID and secret key — copy both immediately
(the secret is only shown once) and store them wherever this deployment's other production
secrets live. They are **not** written to `.env.prod` by any script; that file only holds the
`GARAGE_RPC_SECRET` used for the cluster's internal RPC authentication, not S3 application
credentials.

## Verifying

```bash
podman exec -it "$GARAGE" /garage bucket list
podman exec -it "$GARAGE" /garage bucket info bmn-harwat-prod
```

Both should show the `bmn-harwat-prod` bucket with the key from step 3 attached.
