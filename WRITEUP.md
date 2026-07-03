# Home Robot Language Control – Writeup

## Approach & Design Rationale

I structured the system using a **two-layer architecture** that separates language understanding from robot execution. The Large Language Model (Groq GPT-OSS-120B) is responsible only for converting natural language into a structured JSON intent containing the requested action, object, and destination. All robot behaviour is implemented in deterministic Python code.

I intentionally avoided allowing the LLM to generate execution plans. Instead, every request passes through a decision layer that performs validation, grounding, safety checks, ambiguity handling, recovery, and capability checking before interacting with the simulator. This separation makes the behaviour predictable, easier to debug, and significantly reduces the possibility of unsafe or hallucinated actions.

The final implementation supports five intent categories:

- **Bring** – fetch an object for the user.
- **Move** – relocate an object to a specified destination.
- **Query** – answer questions about object or location states.
- **Chat** – respond to capability-related questions.
- **Unsupported** – politely decline requests outside the robot's abilities.

---

## Key Features

### Grounded Execution

The robot only acts on objects it has verified through sensing. Before manipulating an object, it searches a predefined sequence of locations until the object is observed. Once discovered, the object's location is stored in memory, allowing future requests to navigate directly to the known location without repeating the full search. Whenever an object is moved, the stored location is updated to keep the world model consistent.

### Safety

Safety decisions are handled entirely within the Python decision layer. The robot refuses requests involving potentially dangerous objects such as knives, medications, chemicals, electrical appliances, and weapons. Both exact and partial name matching are used to prevent unsafe requests from bypassing the safety filter. Unsupported requests are rejected with a clear explanation rather than attempting unsafe behaviour.

### Ambiguity Handling

Instead of making assumptions, the robot asks clarification questions whenever a request is genuinely ambiguous. For example, a request such as *"Get me something to drink"* prompts the robot to ask whether the user wants the water bottle or the juice box rather than selecting one automatically.

### Context Awareness

The implementation maintains lightweight conversational context by remembering the last referenced object. This enables natural interactions such as:

- "Bring me the book."
- "Put it in the bedroom."

where **"it"** is resolved to the previously handled object.

### Recovery

The simulator includes probabilistic grasp failures. To improve robustness, the robot retries failed pickup attempts before reporting failure. It also checks whether it is already holding another object and places it before attempting to pick up a new one.

### Environment Queries

Beyond manipulation, the robot can answer questions about its environment using its internal world model, such as:

- "Where is the newspaper?"
- "What is in the bedroom?"

These answers are generated from verified observations rather than inferred by the language model.

---

## Trade-offs

Throughout the implementation I intentionally prioritised **safety and correctness over efficiency**.

The robot prefers asking for clarification rather than guessing missing information, and it refuses actions that cannot be safely verified. Although this can make interactions slightly longer, it prevents incorrect or unsafe behaviour.

Similarly, the object search strategy follows a fixed sequence of locations. While this is not the most efficient search strategy, it provides deterministic behaviour that is easy to understand, reproduce, and debug.

---

## Limitations & Future Work

Although the implementation performs well within the simulator, there are several possible improvements:

- Replace the fixed search order with adaptive search planning based on previous observations.
- Maintain richer multi-turn conversational context instead of only remembering the last referenced object.
- Learn user preferences over time to reduce unnecessary clarification questions.
- Improve recovery by dynamically replanning after repeated failures instead of using fixed retry attempts.
- Support more complex multi-step instructions involving multiple objects and sequential goals.

---

## Summary

The final system combines the flexibility of a Large Language Model for natural language understanding with deterministic Python logic for robot control. By separating intent parsing from execution, the robot remains grounded in verified observations, handles ambiguity conservatively, recovers gracefully from failures, maintains a consistent internal world model, and prioritises safety throughout its decision-making process.