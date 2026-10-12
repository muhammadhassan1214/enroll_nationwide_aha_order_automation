import csv
import os
import logging
from typing import Dict, Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

class AvailableCourses:
    def __init__(self):
        self.available_courses = {}
        self.course_categories = {}  # SKU -> True (individual) / False (bundle)
        self.csv_path = os.path.join('data', 'courses.csv')
        self._load_courses_from_csv()

    def _load_courses_from_csv(self) -> bool:
        """Load courses from CSV file with comprehensive error handling."""
        try:
            if not os.path.exists(self.csv_path):
                logger.error(f"Courses CSV file not found: {self.csv_path}")
                self._load_fallback_courses()
                return False

            with open(self.csv_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                # Validate CSV headers
                required_headers = ['SKU', 'Name', 'Category']
                if not all(header in reader.fieldnames for header in required_headers):
                    logger.error(f"CSV missing required headers. Expected: {required_headers}, Found: {reader.fieldnames}")
                    self._load_fallback_courses()
                    return False

                courses_loaded = 0
                for row_num, row in enumerate(reader, start=2):  # Start at 2 because of header
                    try:
                        sku = row.get('SKU', '').strip()
                        name = row.get('Name', '').strip()
                        category_str = row.get('Category', '').strip().lower()

                        # Validate required fields
                        if not all([sku, name, category_str]):
                            logger.warning(f"Row {row_num}: Missing required fields - SKU: '{sku}', Name: '{name}', Category: '{category_str}'")
                            continue

                        # Parse category boolean
                        if category_str in ['true', '1', 'yes', 'individual']:
                            category = True
                        elif category_str in ['false', '0', 'no', 'bundle']:
                            category = False
                        else:
                            logger.warning(f"Row {row_num}: Invalid category value '{category_str}' for SKU {sku}. Expected True/False")
                            continue

                        # Store course data
                        self.available_courses[sku] = name
                        self.course_categories[sku] = category
                        courses_loaded += 1

                        logger.debug(f"Loaded course: {sku} -> {name} ({'Individual' if category else 'Bundle'})")

                    except Exception as e:
                        logger.error(f"Error processing CSV row {row_num}: {e}")
                        continue

                if courses_loaded > 0:
                    logger.info(f"Successfully loaded {courses_loaded} courses from CSV")
                    return True
                else:
                    logger.error("No valid courses found in CSV file")
                    self._load_fallback_courses()
                    return False

        except FileNotFoundError:
            logger.error(f"Courses CSV file not found: {self.csv_path}")
            self._load_fallback_courses()
            return False
        except Exception as e:
            logger.error(f"Error reading courses CSV: {e}")
            self._load_fallback_courses()
            return False

    def _load_fallback_courses(self):
        """Load fallback hardcoded courses if CSV fails."""
        logger.warning("Loading fallback hardcoded courses")
        self.available_courses = {
            "20-3001": "BLS Provider",
            "20-3002": "Heartsaver First Aid CPR AED",
            "20-3004": "Heartsaver CPR AED",
            "20-3005": "Heartsaver First Aid",
            "20-3011": "Heartsaver for K-12 Schools",
            "20-3016": "BLS Instructor",
            "20-3018": "Advisor: BLS"
        }
        # Assume all fallback courses are individual courses
        self.course_categories = {sku: True for sku in self.available_courses.keys()}

    def is_course_available(self, product_code: str) -> bool:
        """Check if a course is available."""
        if not product_code:
            return False
        return product_code in self.available_courses

    def course_name_on_eCard(self, product_code: str) -> Optional[str]:
        """Get the course name for eCard display."""
        if not product_code:
            return None
        return self.available_courses.get(product_code)

    def is_individual_course(self, product_code: str) -> bool:
        """Check if a course is an individual course (True) or bundle (False)."""
        if not product_code:
            return True  # Default to individual if unknown
        return self.course_categories.get(product_code, True)

    def is_bundle_course(self, product_code: str) -> bool:
        """Check if a course is a bundle course."""
        return not self.is_individual_course(product_code)

    def get_course_info(self, product_code: str) -> Tuple[Optional[str], bool]:
        """Get both course name and category in one call."""
        if not product_code or product_code not in self.available_courses:
            return None, True  # Default to individual if not found

        name = self.available_courses[product_code]
        is_individual = self.course_categories.get(product_code, True)
        return name, is_individual

    def get_preferred_assignment_type(self, product_code: str) -> str:
        """Get preferred assignment type based on course category."""
        if self.is_individual_course(product_code):
            return "instructor"
        else:
            return "training_site"

    def reload_courses(self) -> bool:
        """Reload courses from CSV file."""
        logger.info("Reloading courses from CSV file")
        self.available_courses.clear()
        self.course_categories.clear()
        return self._load_courses_from_csv()

    def get_all_courses(self) -> Dict[str, Dict[str, any]]:
        """Get all courses with their details."""
        result = {}
        for sku in self.available_courses:
            result[sku] = {
                'name': self.available_courses[sku],
                'category': 'Individual' if self.course_categories.get(sku, True) else 'Bundle',
                'is_individual': self.course_categories.get(sku, True)
            }
        return result

    def get_courses_by_category(self, is_individual: bool) -> Dict[str, str]:
        """Get courses filtered by category."""
        filtered_courses = {}
        for sku, name in self.available_courses.items():
            if self.course_categories.get(sku, True) == is_individual:
                filtered_courses[sku] = name
        return filtered_courses
