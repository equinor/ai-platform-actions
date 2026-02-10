---
name: ai-requirements
description: This file specifies which principles that MUST be adhered to when altering any of the files in the repository. It contains requirements for architecture, for structure and for formatting.
---

## Architecture
Each of the actions must be usable by their own.
There should, if possible, be a common set of arguments to input on the actions.
Each action should contain
- A step logging compact summary of what is about to happen
- A step doing input validation. On issues with the input, log informative output
- One or more steps (fewer are better) doing the actual work
- A step printing the results obtained. (If relevant, with direct links to the AzureML workspace)

## Structure
Each action is structured as a verb-object folder.
The two verbs we aim for are deploy and share, although other possibilities are possible if well argued for.
The objects we aim for are the different asset types in AzureML. In addition, there is the x object, where x is a placeholder for one of the others.

## Formatting
- Code comments:
    - As a principle, avoid comments in the code. Exceptions should only occur where it is strictly necessary for clarity. 
- Logs statements:
    - As a principle, any logged statement must be as informative as possible.
    - This means that all information printed must be informative, concise and compact.
    - Usage of icons should be kept limited to ❌and ✅.
- Documentation:
    - Include example code blocks
    - List arguments to be used
    - Include links to MS documentation where relevant

## Other requirements

### Avoid
- Altering files not referenced in the in the prompt. Ask for permission if unsure.

## Do
- Keep code legible and transparent
- In code, aim for modularity, such that if code needs to be changed later, that may be done in an iterative fashion.
- Keep clarity on control flow
- Readability is important
