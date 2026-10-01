# Building and Evaluating RAG Solutions with Azure AI Search — course repo

Exercise files for the course. Module 1 is a demonstration — you can watch it with no setup. Do the setup below before Module 2, where you build the index yourself.

## Prerequisites

- Python 3.9 or later, and `pip`.
- An Azure subscription with permission to create resources and assign roles (Owner, or Contributor + User Access Administrator, on the subscription or a resource group).
- Comfort with resource groups and the Azure portal, at the AZ-900 level. This course does not teach Azure fundamentals.

## 1. Install the Azure CLI

Follow the install guide for your OS: https://learn.microsoft.com/cli/azure/install-azure-cli

Confirm it installed:

```
az --version
```

## 2. Sign in and confirm your subscription

```
az login
az account show
```

`az account show` must print a subscription. If it prints an error or an empty result, you do not have a usable subscription yet. Get one before you continue — for example, the free account at https://azure.microsoft.com/free.

If you have more than one subscription, pick the one this course should use:

```
az account set --subscription "<name-or-id>"
```

## 3. Set up the Python environment

From the repo root:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Provision the Azure resources

```
./infra/deploy.sh
```

This creates a resource group with Azure AI Search, Azure Storage, and an Azure AI Services resource with the model deployments this course needs. At the end, the script writes your settings to a `.env` file in the repo root. You do not copy or paste anything.

Run it once. If a deployment already exists (a `.env` file, or a Search service in the resource group), the script stops before it creates anything, so you are not billed twice. To start over, delete the resource group first. To create a second set on purpose, run `FORCE_ENV=1 ./infra/deploy.sh`. The script keeps your old `.env` as `.env.bak`.

**Cost note:** the Search service runs on the Basic tier, priced per month. Delete the resource group when you are done with the course:

```
az group delete --name <resource-group-from-deploy.sh> --yes
```

## 5. Download the demo corpus

```
./data/download.sh
```

## 6. Confirm everything works

Open `setup/00_setup.ipynb` and run every cell. The last cell confirms your Search service, Blob Storage, and embedding deployment are all reachable, and uploads the demo corpus.

If a cell fails, fix that error before you continue. Do not skip ahead.

## 7. Find your values and check your data in the browser

`deploy.sh` writes the `.env` values for you. You only need this section to find a value again, or to see the data with your own eyes in the browser. Menu labels in Azure change from time to time, so look for the closest match.

**Where each `.env` value lives**

| `.env` value | Where to find it |
|---|---|
| `AZURE_SEARCH_ENDPOINT` | [Azure portal](https://portal.azure.com) > your resource group > the Search service > **Overview** > **Url** |
| `AZURE_STORAGE_ACCOUNT_URL` | Azure portal > the storage account > **Settings** > **Endpoints** > **Blob service** |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_AI_SERVICES_ENDPOINT`, `AZURE_AI_SERVICES_KEY` | Azure portal > the AI Services resource > **Resource Management** > **Keys and Endpoint** |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | [Microsoft Foundry portal](https://ai.azure.com) > your project > **Models + endpoints**. The deployment name is in the **Name** column. |
| `AZURE_SUBSCRIPTION_ID` | Azure portal > **Subscriptions** |

The AI Services key is the only secret in `.env`. Never commit `.env`. It is already in `.gitignore`.

**Check your data**

1. After `setup/00_setup.ipynb`: open the storage account > **Data storage** > **Containers** > `docs`. You must see one folder per state, each holding a PDF.
2. After Module 2: open the Search service > **Search management** > **Indexes** > `state-driver-manuals`. **Document count** must be greater than 0.
3. On that same index, open **Search explorer** and run a query such as `school zone speed limit`. You must see chunks with a `state` value.

If a count is 0 or a folder is missing, go back to the notebook step that creates it. Do not move on.

## What to do next

- Watch Module 1. It needs no setup from you — it runs against a finished index the instructor already built.
- Start Module 2 with `module-2/02_indexing_pipeline.ipynb`. This is where you build the index yourself.
- Continue to Module 3 with `module-3/03_grounded_and_eval.ipynb`.

## Repo layout

```
config.py              # shared settings, loaded by every notebook
requirements.txt       # pinned Python packages
.env.example           # copy to .env and fill in
infra/deploy.sh         # provisions the Azure resources
data/                   # demo corpus (US state driver's manuals) and download script
eval/                   # evaluation question set (Module 3)
setup/                  # 00_setup.ipynb, run once before Module 2
module-1/               # Module 1 notebook
module-2/               # Module 2 notebook
module-3/               # Module 3 notebook
```
