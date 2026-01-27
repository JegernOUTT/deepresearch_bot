# Deep Research Bot

A multi-step investigation bot that produces detailed research reports on any topic.

## Purpose

Performs comprehensive research using web search, academic papers, and GitHub repositories. Asks clarifying questions to understand scope and focus, then investigates sources in parallel to produce a detailed report.

## Target Users

- Individual researchers
- Technical professionals needing deep dives
- Anyone requiring structured investigation with cited sources

## How It Works

### Starting Research

1. **Via Flexus UI**: Send a message describing the research topic
2. **Via Slack**: Message the bot or mention it in a channel

### Research Process

1. Bot asks clarifying questions:
   - What specific aspects to focus on?
   - What's the primary goal? (comparison, implementation guide, landscape analysis, etc.)
   - Any sources to prioritize or avoid?
   - Target audience for the report?

2. Bot investigates (takes ~20-30 minutes):
   - Searches web sources
   - Reviews academic papers
   - Examines relevant GitHub repositories
   - Targets ~25 quality sources
   - No progress updates (runs silently)

3. Produces detailed report with:
   - Executive summary
   - Key findings organized by theme
   - Source citations with links
   - Recommendations or conclusions

### Delivery

- Report saved as policy document in Flexus
- Slack notification when complete
- Optional: post to configured Slack channel

## Configuration

### Required Setup

- **Slack Bot Token**: For receiving messages and sending notifications
- **Slack Notification Channel**: Where to post completed reports
- **Web Search API**: Access to search engines for source discovery
- **Academic Paper Access**: API keys for paper databases (e.g., Semantic Scholar, arXiv)

### Optional Setup

- **GitHub Token**: For deeper repository analysis
- **Report Template**: Custom formatting preferences

## Task Management

- Uses kanban board (inbox → todo → in progress → done)
- Processes one research task at a time (resource-intensive)
- Incoming requests queue in inbox
- Bot picks from todo on schedule (every 30 minutes)

## Data Sources

1. **Web Search**: General information, news, documentation
2. **Academic Papers**: Research papers, technical publications
3. **GitHub**: Code examples, implementations, project analysis

## Report Structure

Each report includes:

```
# [Research Topic]

## Executive Summary
[2-3 paragraph overview]

## Research Questions
[Questions clarified with user]

## Key Findings
### [Theme 1]
[Findings with citations]

### [Theme 2]
[Findings with citations]

## Sources
[Numbered list with links and brief descriptions]

## Conclusions
[Synthesis and recommendations]

## Metadata
- Research date
- Sources reviewed
- Time invested
```

## Limitations

- Medium-depth research (~25 sources, ~30 minutes)
- No real-time progress updates
- One task at a time
- Requires API access to external services
- English-language sources prioritized

## Example Use Cases

- "Research best practices for implementing OAuth2 in microservices"
- "Compare Rust vs Go for systems programming in 2026"
- "Investigate recent advances in graph neural networks"
- "Analyze security vulnerabilities in container orchestration"

## Future Enhancements

- Configurable depth levels (fast/medium/deep)
- Scheduled recurring research topics
- Progress updates during research
- Custom source preferences per request
- Multi-language support