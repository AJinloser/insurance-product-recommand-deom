# Aliyun Server Deployment

## Target Setup
This project runs as a standalone FastAPI service on an Alibaba Cloud server and listens on a single custom port such as `18080`. The existing application on ports `80/443` stays unchanged. No Nginx, Docker, or domain setup is required.

## Server Preparation
On Ubuntu or Debian, install the runtime:

```bash
sudo apt update
sudo apt install -y python3 python3-venv
```

Upload the repository to the server, for example:

```bash
sudo mkdir -p /opt/insurance-product-recommand-demo
sudo chown -R $USER:$USER /opt/insurance-product-recommand-demo
```

## App Setup
Inside the project directory:

```bash
cd /opt/insurance-product-recommand-demo
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create an environment file at `/etc/insurance-recommend.env`:

```bash
INSURANCE_LLM_API_KEY=your_api_key
INSURANCE_LLM_MODEL=gpt-4o
# Optional for OpenAI-compatible gateways
INSURANCE_LLM_BASE_URL=
```

## Start Command
Run the service manually with:

```bash
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 18080
```

The site will be reachable at `http://<server-ip>:18080/`.

## systemd Service
Use [`deploy/insurance-recommend.service`](/home/ajin/insurance-product-recommand-demo/deploy/insurance-recommend.service) as the service definition:

```bash
sudo cp deploy/insurance-recommend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable insurance-recommend
sudo systemctl start insurance-recommend
```

Useful commands:

```bash
sudo systemctl restart insurance-recommend
sudo systemctl status insurance-recommend
journalctl -u insurance-recommend -f
```

## Network
Open port `18080` in both places if needed:
- Alibaba Cloud Security Group
- Local firewall such as `ufw`

Example:

```bash
sudo ufw allow 18080/tcp
```

## Verification
Check the service locally:

```bash
curl http://127.0.0.1:18080/health
```

Then open:
- `http://<server-ip>:18080/`
- `http://<server-ip>:18080/health`

## Updates
For later updates:

```bash
cd /opt/insurance-product-recommand-demo
git pull
. .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart insurance-recommend
```
