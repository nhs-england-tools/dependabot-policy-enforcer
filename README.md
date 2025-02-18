# Dependabot Policy Enforcer

[![CI/CD Pull Request](https://github.com/nhs-england-tools/dependabot-policy-enforcer/actions/workflows/cicd-1-pull-request.yaml/badge.svg)](https://github.com/nhs-england-tools/dependabot-policy-enforcer/actions/workflows/cicd-1-pull-request.yaml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=nhsdigital_nhs-england-tools_dependabot-policy-enforcer&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=nhsdigital_nhs-england-tools_dependabot-policy-enforcer)

A GitHub Action that enforces age-based policies on Dependabot security alerts. It helps teams maintain security by ensuring that vulnerabilities are addressed within specified timeframes based on their severity.

- Checks open Dependabot alerts against configurable age thresholds
- Supports different thresholds for Critical, High, Medium, and Low severity alerts
- Provides detailed reports in PR comments and workflow logs
- Optional report-only mode for monitoring without failing builds

## Table of Contents

- [Dependabot Policy Enforcer](#dependabot-policy-enforcer)
  - [Table of Contents](#table-of-contents)
  - [Setup](#setup)
    - [Prerequisites](#prerequisites)
    - [Configuration](#configuration)
  - [Usage](#usage)
    - [Testing](#testing)
  - [Design](#design)
    - [Diagrams](#diagrams)
    - [Modularity](#modularity)
  - [Contributing](#contributing)
  - [Contacts](#contacts)
  - [Licence](#licence)

## Setup

Clone the repository

```shell
git clone https://github.com/nhs-england-tools/dependabot-policy-enforcer.git
cd nhs-england-tools/dependabot-policy-enforcer
```

### Prerequisites

The following software packages, or their equivalents, are expected to be installed and configured:

- [Python](https://www.python.org/downloads/release/python-3120/) 3.12 or later,

The GitHub action needs to run as a GitHub App to have the required permissions to report on Dependabot findings. To create the app:

From the context of the organisation navigate to `Settings`. In the Organization settings navigate to `Developer settings` and select `GitHub Apps`. Press the `New GitHub App` button. Complete the Register new GitHub App page with the following values:

- `GitHub App name`: `dependabot-policy-enforcer`
- `Homepage URL`: The URL of the repository
- `Webhook`: deselect the `Active` checkbox

Repository permissions:

- `Dependabot alerts: Read-only` to access Dependabot alerts
- `Metadata: Read-only` default permission
- `Pull requests: Read and Write` to add comments to PRs

`Where can this GitHub App be installed?`: select `Any account`

Press the `Create GitHub App` button.

Make a note of the App ID. This will need to be added as a secret to the target repository - or as an organisation level secret.

#### Generate a private key

From the app settings screen press the `Generate a private key` button. This will download a private key pem file to your local machine. This will need adding as a secret to the target repository. Copy the text including the `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----` be aware that the pem file will include a blank line at the end - this should not be included into the secret.

#### Install app

From the app settings screen select `Install App` link. You will be prompted to select an account to install the app on. Locate the organization you want to install to and press the `Install` button next to this organization.

Select to install the app at `All repositories` press the `Install` button. The installation ID is included in the URL after `/settings/installations/` this needs adding to the Secrets for the target repository or organizations.

### Configuration

Installation and configuration of the toolchain dependencies

```shell
make config
```

### Local development

#### Setting up a Python virtual environment

To set up a Python virtual environment and install the dependencies listed in `requirements.txt`, follow these steps:

1. Create a virtual environment:

    ```shell
    pip install --upgrade pip
    python -m venv venv
    ```

2. Activate the virtual environment:

    - On Windows:

        ```shell
        .\venv\Scripts\activate
        ```

    - On macOS and Linux:

        ```shell
        source venv/bin/activate
        ```

3. Install the dependencies:

    ```shell
    pip install -r requirements.txt
    ```

#### Running the tests

To run the tests, follow these steps:

1. Ensure the virtual environment is activated (see above).

2. Run the tests using `unittest`:

    ```shell
    python -m unittest discover -s . -p "test_check_alerts.py"
    ```

This will execute the unit tests and display the results in the terminal.

## Usage

To use this action it is recommended to install the app at the organisation level with access to `All repositories`.

When the app has been installed you will need the installation ID - this is the final part of the URL on the page following installation of the app.

From the organisation, select `Secrets and variables` in the left hand side navigation column. Now select `Actions`. You will need to create three new organization secrets, with Repository access set to `All repositories`:

1. DEPENDABOT_POLICY_ENFORCER_APP_ID
1. DEPENDABOT_POLICY_ENFORCER_INSTALLATION_ID
1. DEPENDABOT_POLICY_ENFORCER_PRIVATE_KEY

Next you will need to configure a ruleset to ensure this workflow executes on every PR.

## Configuring a ruleset

Navigate to the organisation that you want to create the ruleset for. Select Settings and look for Repository in the left hand navigation, select this and select Rulesets. press the `New ruleset` button. Select `New branch ruleset`. Give this new ruleset a name - e.g. `dependabot-policy-enforcer`. select Enforcement status of `Evaluate`.

We now need to select Targets for the ruleset. Here we will use custom properties and only apply this to repositories that have a specific [custom property](https://docs.github.com/en/enterprise-cloud@latest/organizations/managing-organization-settings/creating-rulesets-for-repositories-in-your-organization#targeting-repositories-by-properties-in-your-organization) set. To do this, under Targets select `Include repositories by property`, under the Property drop down select an appropriate property - for example `Property: SubDirectorate` under the Value drop down select the appropriate value for your needs. Note this assumes that your organisation uses custom properties and has values set appropriately. Press `Add target`.

Under Bypass list we need to exclude Dependabot from these runs as the permissions are configured such that Dependabot has its own set of secrets. Press `Add bypass` and search for Dependabot - place a check mark next to this bot entry.

Under `Target branches` select to add a target and choose the All branches option.

### Configuring the Branch rules

Remove the check mark against the Restrict deletions rule.
Remove the check mark against the Block force pushes rule.
Add a check mark against the Require workflows to pass before merging rule.
Press the `Add workflow` button and select the `org-workflows` repository created earlier. Select the main branch to ensure only peer reviewed changes are used. in pick a workflow file enter the following `.github/workflows/dependabot-policy-enforcer.yml` press `Add workflow`

Press the `Create` button.

The GitHub UI will advise that the Ruleset has been created.

## Create a reusable workflow for your organisation

Create a new public repository in your organisation, or reuse an existing one, for example `org-workflows`

Create a file in this repository: `.github/workflows/dependabot-policy-enforcer.yml` and add the yaml below:

```yaml
name: Check Dependabot Alerts
on:
  pull_request:
    types: [opened, synchronize, reopened]
  workflow_dispatch:

permissions:
  security-events: read
  contents: read
  pull-requests: write  # Required for PR comments

jobs:
  check-alerts:
    runs-on: ubuntu-latest
    steps:
      - uses: nhs-england-tools/dependabot-policy-enforcer
        with:
          github-app-id: ${{ secrets.DEPENDABOT_POLICY_ENFORCER_APP_ID }}
          github-installation-id: ${{ secrets.DEPENDABOT_POLICY_ENFORCER_INSTALLATION_ID }}
          github-app-private-key: ${{ secrets.DEPENDABOT_POLICY_ENFORCER_PRIVATE_KEY }}
          critical-threshold: 3
          high-threshold: 5
          medium-threshold: 14
          low-threshold: 30
          report-mode: true
```

### Permissions

This action requires:

- `security-events: read` to access Dependabot alerts
- `contents: read` to access repository content
- `pull-requests: write` (optional) to post comments on PRs

App permissions:

- `Dependabot alerts: Read` to access Dependabot alerts
- `Metadata: Read` default permission
- `Pull requests: Read and Write` to add comments to PRs

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `github-app-id` | App ID for the GitHub app with the necessary permissions | Yes | N/A |
| `github-installation-id` | Installation ID for the GitHub app at the required organisation | Yes | N/A |
| `github-app-private-key` | Private Key for the GitHub app - note this *must* be stored as a secret | Yes | N/A |
| `critical-threshold` | Maximum age in days for Critical severity alerts | No | 3 |
| `high-threshold` | Maximum age in days for High severity alerts | No | 5 |
| `medium-threshold` | Maximum age in days for Medium severity alerts | No | 14 |
| `low-threshold` | Maximum age in days for Low severity alerts | No | 30 |
| `report-mode` | Run in report-only mode without failing | No | false |

### Testing

The action can be tested locally by running the `main.py` script with appropriate arguments.  Create a `.env` file in the root of the project and populate it with the required environment variables:

```bash
CRITICAL_THRESHOLD=3
HIGH_THRESHOLD=5
MEDIUM_THRESHOLD=14
LOW_THRESHOLD=30
REPORT_MODE=true
```

## Design

### Diagrams

The [C4 model](https://c4model.com/) is a simple and intuitive way to create software architecture diagrams that are clear, consistent, scalable and most importantly collaborative. This should result in documenting all the system interfaces, external dependencies and integration points.

![Repository Template](./docs/diagrams/Repository_Template_GitHub_Generic.png)

The source for diagrams should be in Git for change control and review purposes. Recommendations are [draw.io](https://app.diagrams.net/) (example above in [docs](.docs/diagrams/) folder) and [Mermaids](https://github.com/mermaid-js/mermaid). Here is an example Mermaids sequence diagram:

```mermaid
sequenceDiagram
    User->>+Service: GET /users?params=...
    Service->>Service: auth request
    Service->>Database: get all users
    Database-->>Service: list of users
    Service->>Service: filter users
    Service-->>-User: list[User]
```

### Modularity

Most of the projects are built with customisability and extendability in mind. At a minimum, this can be achieved by implementing service level configuration options and settings. The intention of this section is to show how this can be used. If the system processes data, you could mention here for example how the input is prepared for testing - anonymised, synthetic or live data.

## Contributing

Describe or link templates on how to raise an issue, feature request or make a contribution to the codebase. Reference the other documentation files, like

- Environment setup for contribution, i.e. `CONTRIBUTING.md`
- Coding standards, branching, linting, practices for development and testing
- Release process, versioning, changelog
- Backlog, board, roadmap, ways of working
- High-level requirements, guiding principles, decision records, etc.

## Contacts

Provide a way to contact the owners of this project. It can be a team, an individual or information on the means of getting in touch via active communication channels, e.g. opening a GitHub discussion, raising an issue, etc.

## Licence

> The [LICENCE.md](./LICENCE.md) file will need to be updated with the correct year and owner

Unless stated otherwise, the codebase is released under the MIT License. This covers both the codebase and any sample code in the documentation.

Any HTML or Markdown documentation is [© Crown Copyright](https://www.nationalarchives.gov.uk/information-management/re-using-public-sector-information/uk-government-licensing-framework/crown-copyright/) and available under the terms of the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
