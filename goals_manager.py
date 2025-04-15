class GoalsManager:
    def __init__(self):
        self.predefined_goals = {
            'weight_loss': {
                'calories': 1500,
                'protein': 120,
                'fat': 50,
                'carbs': 150
            },
            'muscle_gain': {
                'calories': 2500,
                'protein': 180,
                'fat': 80,
                'carbs': 250
            },
            'maintenance': {
                'calories': 2000,
                'protein': 150,
                'fat': 65,
                'carbs': 200
            },
            'keto': {
                'calories': 1800,
                'protein': 120,
                'fat': 120,
                'carbs': 30
            }
        }

    def get_predefined_goals(self, goal_type: str) -> dict:
        """Get predefined goals for a specific goal type."""
        return self.predefined_goals.get(goal_type, self.predefined_goals['maintenance'])

    def parse_custom_goals(self, text: str) -> dict:
        """Parse custom goals from text input."""
        try:
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("Invalid format")
            
            return {
                'calories': int(parts[0]),
                'protein': int(parts[1]),
                'fat': int(parts[2]),
                'carbs': int(parts[3])
            }
        except (ValueError, IndexError):
            return self.predefined_goals['maintenance'] 