import json
import os

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def call_llm(system, user):
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system
                },
                {
                    "role": "user",
                    "content": user
                }
            ]
        )

        text = response.choices[0].message.content.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.splitlines()

            if lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines)

        return text

    except Exception as e:
        print("Groq Error:", e)
        print("Falling back to mock LLM...")
        return mock_llm(system, user)


# Temporary fallback if Groq is unavailable
def mock_llm(system, user):
    u = user.lower()

    if "water" in u or "drink" in u or "thirsty" in u:
        return json.dumps({
            "intent": "bring",
            "object": "drink",
            "destination": None
        })

    return json.dumps({
        "intent": "unknown",
        "object": None,
        "destination": None
    })


class Agent:
    def __init__(self, robot):
        self.robot = robot
        self.last_object = None  # Track most recently handled object for pronoun references

        self.search_locations = [
            "kitchen_counter",
            "dining_table",
            "bedside_table",
            "bathroom",
            "desk"
        ]

        self.unsafe_objects = {
            # Sharp objects
            "kitchen_knife",
            "scissors",
            "blade",
            "razor",
            "needle",
            "syringe",
            "tack",
            
            # Medications & chemicals
            "pill_bottle",
            "medication",
            "medicine",
            "aspirin",
            "bleach",
            "cleaner",
            "pesticide",
            "poison",
            "acid",
            "solvent",
            "ammonia",
            
            # Electrical appliances
            "iron",
            "heater",
            "toaster",
            "microwave",
            "saw",
            "drill",
            "chainsaw",
            
            # Fire hazards
            "match",
            "lighter",
            "candle",
            "fireworks",
            "gasoline",
            "lighter_fluid",
            
            # Breakable/dangerous items
            "glass",
            "vase",
            "wine_glass",
            
            # Weapons
            "gun",
            "rifle",
            "knife",
            "weapon",
            "ammunition",
        }

    def handle(self, command):
        system = """
You are an intent parser for a home robot.

Return ONLY valid JSON. No markdown, no explanation, no extra text.

Valid intents: bring, move, chat, query, unsupported

Schema:
{
  "intent": "bring" | "move" | "chat" | "query" | "unsupported",
  "object": string | null,
  "destination": string | null
}

Rules:
1. Return only the JSON object, nothing else.
2. Use null for missing fields.
3. If user asks "What can you do?", return {"intent": "chat", "object": null, "destination": null}.
4. Use "query" when user asks about locations or objects (e.g. "where is X", "what is in Y", "what objects are in Y").
   - For "where is X": set object to the object name, destination to null.
   - For "what is in Y": set object to null, destination to the location name.
5. If user requests unsupported actions (open windows, cook, clean, etc.), return {"intent": "unsupported", "object": null, "destination": null}.
6. Use "bring" when the user wants an object fetched without specifying a destination (e.g. "get me X", "bring me X", "bring X").
7. Use "move" when the user explicitly specifies BOTH an object AND a destination location (e.g. "take X to Y", "move X to Y", "put X in Y", "keep it in Y").
8. Recognize "place", "put", "keep", "leave", "store" as move intents (destination required).
9. If user uses pronouns like "it", "that", "this" without an explicit object name, set object to null (will be filled by context later).
10. For ambiguous drink requests without a specific object, return {"intent": "bring", "object": "drink", "destination": null}.
11. Extract both object and destination when present. Do not ignore a destination.
12. Normalize location names: remove "my", "the", possessive prefixes. E.g. "my bedroom" → "bedroom", "the kitchen" → "kitchen".
        """

        raw = call_llm(system, command)

        try:
            intent = json.loads(raw)
        except json.JSONDecodeError:
            self.robot.speak("Sorry, I couldn't understand your request.")
            self._display_response()
            return

        self.execute_intent(intent)
        self._display_response()

    #################################################

    #################################################

    def execute_intent(self, intent):
        """Route the parsed intent to the appropriate action."""
        action = intent.get("intent")
        obj = intent.get("object")
        destination = intent.get("destination")

        # If object is null, check robot's current holding, then fall back to last handled object
        if obj is None:
            if self.robot.holding is not None:
                obj = self.robot.holding
            elif self.last_object is not None:
                obj = self.last_object

        if action == "bring":
            # Handle ambiguous drink request
            if obj == "drink":
                self.ask_clarification(
                    "Would you like the water bottle or the juice box?"
                )
                return

            if obj is None:
                self.ask_clarification("What would you like me to bring?")
                return

            self.bring_object(obj)

        elif action == "move":
            if obj is None or destination is None:
                self.ask_clarification("Please tell me what to move and where.")
                return

            self.move_object(obj, destination)

        elif action == "query":
            if obj is not None:
                # Query: where is this object?
                self.query_object(obj)
            elif destination is not None:
                # Query: what is in this location?
                self.query_location(destination)
            else:
                self.ask_clarification("What would you like to know?")

        elif action == "chat":
            self.robot.speak(
                "I can move around the apartment, pick up objects, place them down, and speak."
            )

        elif action == "unsupported":
            self.robot.speak(
                "I'm sorry, I can't perform that action."
            )

        else:
            self.robot.speak("Sorry, I don't know how to help with that.")

    #################################################

    def bring_object(self, obj):
        """Fetch an object and bring it to the user (living room)."""
        # Normalize object name (convert spaces to underscores)
        obj = obj.replace(" ", "_")
        display_name = obj.replace("_", " ")
        
        # Track this object for future pronoun references
        self.last_object = obj

        # Safety check
        if not self.safety_check(obj):
            return

        # Search for the object
        location = self.search_object(obj)
        if location is None:
            self.robot.speak(f"I searched the apartment but couldn't find the {display_name}.")
            return

        # Attempt to pick up with retries
        if not self.retry_pick(obj, display_name):
            self.robot.speak(f"I couldn't pick up the {display_name}. Please try again later.")
            return

        # Navigate to delivery location (user's assumed location)
        result = self.robot.navigate_to("living_room")
        if not result:
            self.robot.speak("I couldn't reach the living room.")
            return

        # Place the object and confirm completion
        result = self.robot.place()
        if result:
            # Update known_objects to reflect the new location
            if obj in self.robot.known_objects:
                self.robot.known_objects[obj]["location"] = "living_room"
            self.robot.speak(f"I've placed the {display_name} in the living room for you.")

    #################################################

    def search_object(self, obj):
        """
        Search for an object, checking known objects first to avoid unnecessary exploration.
        Return the actual object location if found, None otherwise.
        """
        # First check if we already know about this object
        if obj in self.robot.known_objects:
            actual_location = self.robot.known_objects[obj]["location"]
            
            
            # Navigate there if not already present
            if self.robot.current_location != actual_location:
                self.robot.navigate_to(actual_location)
            
            return actual_location
        
        # Object not known, begin exploration
        for location in self.search_locations:
            result = self.robot.navigate_to(location)
            
            if not result:
                continue
            
            # After navigating, check if the object has been sensed
            if obj in self.robot.known_objects:
                actual_location = self.robot.known_objects[obj]["location"]
                
                
                # Navigate to actual location if necessary
                if self.robot.current_location != actual_location:
                    self.robot.navigate_to(actual_location)
                
                return actual_location
        
        return None

    def retry_pick(self, obj, display_name=None):
        """
        Attempt to pick the object with retries.
        Announce retries to the user.
        Return True on success, False on all failures.
        """
        if display_name is None:
            display_name = obj.replace("_", " ")

        # If already holding something, place it first
        if self.robot.holding is not None:
            result = self.robot.place()
            if not result:
                self.robot.speak("I need to put down what I'm holding first.")
                return False

        max_retries = 3
        for attempt in range(max_retries):
            result = self.robot.pick(obj)
            if result:
          
                return True
       
            if attempt < max_retries - 1:
                self.robot.speak("Retrying to pick it up...")

        return False

    def safety_check(self, obj):
        """
        Reject unsafe objects.
        Check both exact matches and partial matches (e.g., "knife" matches "kitchen_knife").
        Return True if safe, False if unsafe (and speak refusal).
        """
        # Check exact match
        if obj in self.unsafe_objects:
            self.robot.speak("I'm sorry, I can't hand over potentially dangerous objects.")
            return False
        
        # Check partial match - if requested object name appears in any unsafe object
        for unsafe_obj in self.unsafe_objects:
            if obj in unsafe_obj:
                self.robot.speak("I'm sorry, I can't hand over potentially dangerous objects.")
                return False
        
        return True

    def move_object(self, obj, destination):
        """
        Move an object to a destination.
        Validates destination, searches, picks, navigates, and places.
        """
        # Normalize object name (convert spaces to underscores)
        obj = obj.replace(" ", "_")
        destination = destination.replace(" ", "_")
        
        # Track this object for future pronoun references
        self.last_object = obj
        
        # Normalize possessive prefixes ("my_bedroom" → "bedroom", "the_kitchen" → "kitchen")
        for prefix in ["my_", "the_"]:
            if destination.startswith(prefix):
                destination = destination[len(prefix):]
        
        obj_display = obj.replace("_", " ")
        dest_display = destination.replace("_", " ")

        # Validate destination exists
        if destination not in self.robot.known_locations:
            self.robot.speak(f"I don't know where '{dest_display}' is.")
            return

        # Safety check
        if not self.safety_check(obj):
            return

        # Search for the object
        location = self.search_object(obj)
        if location is None:
            self.robot.speak(f"I searched the apartment but couldn't find the {obj_display}.")
            return

        # Attempt to pick up with retries
        if not self.retry_pick(obj, obj_display):
            self.robot.speak(f"I couldn't pick up the {obj_display}.")
            return

        # Navigate to the destination
        result = self.robot.navigate_to(destination)
        if not result:
            self.robot.speak("I couldn't reach that location.")
            return

        # Place the object and confirm completion
        result = self.robot.place()
        if result:
            # Update known_objects to reflect the new location
            if obj in self.robot.known_objects:
                self.robot.known_objects[obj]["location"] = destination
            self.robot.speak(f"I've moved the {obj_display} to the {dest_display}.")

    def ask_clarification(self, message):
        """Ask the user a clarification question."""
        self.robot.speak(message)

    def query_object(self, obj):
        """Answer 'where is this object?' based on known_objects."""
        obj = obj.replace(" ", "_")
        display_name = obj.replace("_", " ")

        if obj in self.robot.known_objects:
            location = self.robot.known_objects[obj]["location"]
            location_display = location.replace("_", " ")
            self.robot.speak(f"The {display_name} is in the {location_display}.")
        else:
            self.robot.speak(f"I haven't seen the {display_name} yet. Would you like me to search for it?")

    def query_location(self, location):
        """Answer 'what is in this location?' based on known_objects."""
        location = location.replace(" ", "_")
        location_display = location.replace("_", " ")

        # Normalize possessive prefixes
        for prefix in ["my_", "the_"]:
            if location.startswith(prefix):
                location = location[len(prefix):]
                location_display = location.replace("_", " ")

        # Find all objects in this location
        objects_here = [obj for obj, info in self.robot.known_objects.items() if info["location"] == location]

        if not objects_here:
            self.robot.speak(f"I don't know of any objects in the {location_display}.")
        else:
            objects_display = ", ".join([obj.replace("_", " ") for obj in objects_here])
            self.robot.speak(f"I've seen these objects in the {location_display}: {objects_display}.")

    def _display_response(self):
        """Display robot's response in interactive mode (when no renderer is active)."""
        if self.robot._last_speech and self.robot._renderer is None:
            print(f'Robot: {self.robot._last_speech}')