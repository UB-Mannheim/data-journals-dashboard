# Data Journals Dashboard

## Code walkthrough for local deployment

### Python setup

1. Clone the repository and change to project directory

```bash
git clone https://github.com/UB-Mannheim/data-journals-dashboard.git
cd data-journals-dashboard
```

2. Create a Python venv and activate it

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies

```bash
pip install .
```

4. Test the installation. Running ...

```bash
dj --help
```

... should print to CLI:

```bash
Usage: dj [OPTIONS] COMMAND [ARGS]...

  Data Journal Dashboard CLI Helper.

Options:
  --help  Show this message and exit.

Commands:
  collect   Fetch or parse raw journal metadata from GitHub or a local...
  process   Process raw journal metadata by validating it against the...
  hugo      Generate Hugo static site content from processed journal data.
  export    Export data journal metadata to different file types.
  validate  Validate journals against metadata schema.
```

5. Start and follow the jupyter notebook: `walkthrough.ipynb`
