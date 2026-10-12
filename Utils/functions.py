import re
import os
import csv
import time
import logging
from typing import Optional

from dotenv import load_dotenv
from courses import AvailableCourses


# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables and validate
load_dotenv()

# Required for every run: Enroll Nationwide, eCards (Atlas) and the Discord webhook
REQUIRED_ENV_VARS = [
    "ENW_USERNAME", "ENW_PASSWORD",
    "ATLAS_USERNAME", "ATLAS_PASSWORD", "DISCORD_WEBHOOK_URL",
]

def validate_environment_variables(names: Optional[list] = None) -> bool:
    """Validate that the given (default: all required) environment variables are set."""
    missing_vars = [var for var in (names or REQUIRED_ENV_VARS) if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        return False
    return True

# Initialize available courses with error handling
def get_available_courses():
    """Get available courses instance with error handling."""
    try:
        return AvailableCourses()
    except Exception as e:
        logger.error(f"Failed to initialize AvailableCourses: {e}")
        return None

available_courses = get_available_courses()


def get_training_site_name(code: str) -> Optional[str]:
    """Get training site name from CSV with comprehensive error handling."""
    if not code:
        logger.warning("Empty code provided for training site lookup")
        return None

    csv_path = os.path.join('data', 'training_sites.csv')

    try:
        if not os.path.exists(csv_path):
            logger.error(f"Training sites CSV file not found: {csv_path}")
            return None

        with open(csv_path, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            for row_num, row in enumerate(reader, start=2):  # Start at 2 because of header
                try:
                    if row.get('Code', '').strip() == code.strip():
                        training_site_name = row.get('Text', '').strip()
                        if training_site_name:
                            logger.info(f"Found training site: {code} -> {training_site_name}")
                            return training_site_name
                        else:
                            logger.warning(f"Empty training site name for code: {code}")
                            return None
                except Exception as e:
                    logger.error(f"Error processing CSV row {row_num}: {e}")
                    continue

        logger.warning(f"Training site code not found: {code}")
        return None

    except FileNotFoundError:
        logger.error(f"Training sites CSV file not found: {csv_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading training sites CSV: {e}")
        return None
