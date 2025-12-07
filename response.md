# Deep Dive: Task System Architecture & Implementation

This document outlines exactly how "Normal Tasks" and "Global Tasks" are structured, stored, and managed in the codebase.

## 1. Database Schema Level

The system uses two completely distinct tables for these two types of tasks, though they are presented uniformly to the user.

### A. Normal Tasks (The `tasks` table)
These are dynamic, instance-based tasks usually created by guild administrators.
*   **Table:** `tasks`
*   **Identity:** identified by a `guild_id` and an auto-incrementing **Integer** `task_id`.
*   **Storage:**
    *   `tasks` table: Defines the task (Name, Reward, Duration, etc.).
    *   `user_tasks` table: Tracks user progress (Claimed, In Progress, Submitted, Completed).
*   **Key Column:** `is_global` (Boolean). This flag allows a normal task to be visible across other guilds (see "Guild-Global" below).

### B. System Global Tasks (The `global_tasks` table)
These are permanent, hard-coded system tasks (like "Watch Ad").
*   **Table:** `global_tasks`
*   **Identity:** Identified by a unique **String** `task_key` (e.g., `'ad_claim_task'`).
*   **Storage:**
    *   `global_tasks` table: Defines the static properties (Name, Reward, Cooldown, Type).
    *   `global_task_claims` table: Tracks user claims separately from normal user tasks.
*   **Key Attributes:** `task_type` (e.g., 'ad_claim'), `cooldown_minutes`, `is_repeatable`.

---

## 2. Code Implementation (`core/task_manager.py`)

The `TaskManager` class is the unification layer. It hides the database differences from the frontend/bot commands.

### How they interact (The `get_tasks` method)
This is the most critical interaction point. When a user runs `/tasks` (or the bot fetches tasks), `get_tasks(guild_id)` does the following:

1.  **Fetches Normal Tasks:** Queries the `tasks` table for the specific `guild_id`.
2.  **Fetches "Guild-Global" Tasks:** Queries the `tasks` table for any task where `is_global = true` (excluding the current guild).
3.  **Fetches System Global Tasks:** Queries the `global_tasks` table.
4.  **Unification:** It converts the `global_tasks` rows into a dictionary format that mimics the normal `tasks` structure:
    *   `task_key` (String) becomes `task_id`.
    *   `task_type` is mapped to `category`.
    *   Defaults (like `duration_hours = 24`) are injected to satisfy the normal task schema.
    *   **Sorting:** Global tasks are forced to the top of the list.

### How they differ in Logic (Claiming)

This is where the abstraction breaks and distinct handling is required:

*   **Normal Task Claiming (`claim_task`):**
    *   Accepts `guild_id` and **Integer** `task_id`.
    *   Validates against `tasks` table.
    *   Inserts record into `user_tasks` table.
    *   **Constraint:** Cannot claim String-ID tasks here (it casts ID to int).

*   **Global Task Claiming:**
    *   Because `task_manager.claim_task` casts inputs to `int`, it **cannot** handle System Global Tasks (which have string keys like `ad_claim_task`).
    *   **Handler:** These must be routed to specific managers, such as `core/ad_claim_manager.py`.
    *   **Ad Manager Example:**
        *   `create_ad_session`: This is the equivalent of "claiming" the ad task.
        *   Inserts record into `global_task_claims`.

---

## 3. The "Global" Nuance

There are actually **two** types of "Global" tasks in your system:

1.  **Guild-Global Tasks (From `tasks` table)**
    *   **Code:** defined in `tasks` table with `is_global = true`.
    *   **Purpose:** Allows an admin to create a task in Server A that is visible in Server B.
    *   **Handling:** Handled entirely by `TaskManager`. Users in Server B claim it, and a row is created in `user_tasks` (linked to Server B).

2.  **System-Global Tasks (From `global_tasks` table)**
    *   **Code:** defined in `global_tasks` table.
    *   **Purpose:** Permanent features (Daily rewards, Ads).
    *   **Handling:** `TaskManager` reads them, but specialized managers (like `AdClaimManager`) handle the execution and rewarding.

## 4. Summary Table

| Feature | Normal Tasks | System Global Tasks |
| :--- | :--- | :--- |
| **Source Table** | `tasks` | `global_tasks` |
| **ID Type** | Integer (e.g., `14`) | String (e.g., `ad_claim_task`) |
| **Claim Storage** | `user_tasks` | `global_task_claims` |
| **Creation** | Dynamic (Admin created) | Static (SQL/Hardcoded) |
| **Manager** | `TaskManager` | `AdClaimManager` (or specific handler) |
| **Discovery** | `TaskManager.get_tasks()` | `TaskManager.get_tasks()` |
| **Claim Logic** | `TaskManager.claim_task()` | **Custom** (e.g. `AdClaimManager.create_ad_session`) |
