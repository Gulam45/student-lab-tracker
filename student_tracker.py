#!/usr/bin/env python3
"""Student lab and attendance tracker backed by SQLite."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import TextIO


class StudentTracker:
    """Data access and reporting operations for the tracker."""

    def __init__(self, database_path: str | Path = "student_tracker.db") -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            path = Path(self.database_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.database_path = str(path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        """Create the tables and constraints if this is a new database."""
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS Students (
                    USN TEXT PRIMARY KEY COLLATE NOCASE,
                    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                    semester INTEGER NOT NULL CHECK (semester > 0)
                );

                CREATE TABLE IF NOT EXISTS Attendance (
                    USN TEXT NOT NULL COLLATE NOCASE,
                    date TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
                    lab_marks REAL CHECK (
                        lab_marks IS NULL OR (lab_marks >= 0 AND lab_marks <= 100)
                    ),
                    PRIMARY KEY (USN, date),
                    FOREIGN KEY (USN) REFERENCES Students (USN) ON DELETE CASCADE
                );
                """
            )

    @staticmethod
    def _normalize_usn(usn: str) -> str:
        normalized = usn.strip().upper()
        if not normalized:
            raise ValueError("USN cannot be empty.")
        return normalized

    @staticmethod
    def _validate_date(attendance_date: str | date) -> str:
        if isinstance(attendance_date, datetime):
            raise ValueError("Date must use YYYY-MM-DD format.")
        if isinstance(attendance_date, date):
            return attendance_date.isoformat()
        try:
            parsed = date.fromisoformat(attendance_date.strip())
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Date must use YYYY-MM-DD format.") from error
        if parsed.isoformat() != attendance_date.strip():
            raise ValueError("Date must use YYYY-MM-DD format.")
        return parsed.isoformat()

    def add_student(self, usn: str, name: str, semester: int) -> None:
        """Add a student; duplicate USNs are rejected."""
        normalized_usn = self._normalize_usn(usn)
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Student name cannot be empty.")
        if isinstance(semester, bool) or not isinstance(semester, int) or semester < 1:
            raise ValueError("Semester must be a positive whole number.")
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO Students (USN, name, semester) VALUES (?, ?, ?)",
                    (normalized_usn, clean_name, semester),
                )
        except sqlite3.IntegrityError as error:
            if "Students.USN" in str(error):
                raise ValueError(f"Student {normalized_usn} already exists.") from error
            raise

    def mark_attendance(
        self, usn: str, attendance_date: str | date, status: str
    ) -> None:
        """Record or correct a student's attendance for a day."""
        normalized_usn = self._normalize_usn(usn)
        normalized_date = self._validate_date(attendance_date)
        normalized_status = status.strip().capitalize()
        if normalized_status not in {"Present", "Absent"}:
            raise ValueError("Status must be Present or Absent.")
        student = self.connection.execute(
            "SELECT 1 FROM Students WHERE USN = ?", (normalized_usn,)
        ).fetchone()
        if student is None:
            raise LookupError(f"Student {normalized_usn} was not found.")
        try:
            with self.connection:
                # Correcting attendance leaves previously entered marks intact.
                self.connection.execute(
                    """
                    INSERT INTO Attendance (USN, date, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT (USN, date) DO UPDATE SET status = excluded.status
                    """,
                    (normalized_usn, normalized_date, normalized_status),
                )
        except sqlite3.IntegrityError as error:
            if "Attendance.USN" in str(error):
                raise LookupError(f"Student {normalized_usn} was not found.") from error
            raise

    def enter_lab_marks(
        self, usn: str, attendance_date: str | date, lab_marks: float
    ) -> None:
        """Set a student's lab component mark on an existing attendance date."""
        normalized_usn = self._normalize_usn(usn)
        normalized_date = self._validate_date(attendance_date)
        if isinstance(lab_marks, bool) or not isinstance(lab_marks, (int, float)):
            raise ValueError("Lab marks must be a number from 0 to 100.")
        if not 0 <= lab_marks <= 100:
            raise ValueError("Lab marks must be from 0 to 100.")
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE Attendance SET lab_marks = ?
                WHERE USN = ? AND date = ?
                """,
                (float(lab_marks), normalized_usn, normalized_date),
            )
            if cursor.rowcount == 0:
                student = self.connection.execute(
                    "SELECT 1 FROM Students WHERE USN = ?", (normalized_usn,)
                ).fetchone()
                if student is None:
                    raise LookupError(f"Student {normalized_usn} was not found.")
                raise LookupError(
                    f"No attendance record exists for {normalized_usn} on "
                    f"{normalized_date}; mark attendance first."
                )

    def calculate_percentage(self, usn: str) -> float:
        """Return the attendance percentage, or 0.0 when no sessions exist."""
        normalized_usn = self._normalize_usn(usn)
        student = self.connection.execute(
            "SELECT 1 FROM Students WHERE USN = ?", (normalized_usn,)
        ).fetchone()
        if student is None:
            raise LookupError(f"Student {normalized_usn} was not found.")
        totals = self.connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present
            FROM Attendance WHERE USN = ?
            """,
            (normalized_usn,),
        ).fetchone()
        if totals["total"] == 0:
            return 0.0
        # Every recorded date counts as a session, whether present or absent.
        return round(totals["present"] * 100.0 / totals["total"], 2)

    def export_report(self, csv_path: str | Path) -> int:
        """Export one summary row per student and return the number of rows."""
        output_path = Path(csv_path).expanduser()
        if output_path.exists() and output_path.is_dir():
            raise IsADirectoryError(f"Report path is a directory: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connection.execute(
            """
            SELECT s.USN, s.name, s.semester,
                   COUNT(a.date) AS sessions,
                   COALESCE(SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END), 0)
                       AS present,
                   AVG(a.lab_marks) AS average_lab_marks
            FROM Students AS s
            LEFT JOIN Attendance AS a ON a.USN = s.USN
            GROUP BY s.USN, s.name, s.semester
            ORDER BY s.USN
            """
        ).fetchall()
        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                (
                    "USN",
                    "Name",
                    "Semester",
                    "Attendance Sessions",
                    "Present Sessions",
                    "Attendance Percentage",
                    "Average Lab Marks",
                )
            )
            for row in rows:
                percentage = (
                    round(row["present"] * 100.0 / row["sessions"], 2)
                    if row["sessions"]
                    else 0.0
                )
                average_marks = (
                    round(row["average_lab_marks"], 2)
                    if row["average_lab_marks"] is not None
                    else ""
                )
                writer.writerow(
                    (
                        row["USN"],
                        row["name"],
                        row["semester"],
                        row["sessions"],
                        row["present"],
                        f"{percentage:.2f}",
                        average_marks,
                    )
                )
        return len(rows)

    def list_students(self) -> list[sqlite3.Row]:
        """Return students in USN order for display in the CLI."""
        return self.connection.execute(
            "SELECT USN, name, semester FROM Students ORDER BY USN"
        ).fetchall()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> StudentTracker:
        return self

    def __exit__(self, exception_type: object, exception: object, traceback: object) -> None:
        self.close()


def _read_nonempty(prompt: str, input_stream: TextIO = sys.stdin) -> str:
    while True:
        print(prompt, end="", flush=True)
        value = input_stream.readline()
        if value == "":
            raise EOFError
        value = value.strip()
        if value:
            return value
        print("This field cannot be empty.")


def _read_semester(input_stream: TextIO = sys.stdin) -> int:
    while True:
        try:
            semester = int(_read_nonempty("Semester: ", input_stream))
            if semester < 1:
                raise ValueError
            return semester
        except ValueError:
            print("Enter a positive whole number for semester.")


def _read_marks(input_stream: TextIO = sys.stdin) -> float:
    while True:
        try:
            marks = float(_read_nonempty("Lab marks (0-100): ", input_stream))
            if not 0 <= marks <= 100:
                raise ValueError
            return marks
        except ValueError:
            print("Enter a number from 0 to 100.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Student lab and attendance tracker")
    parser.add_argument(
        "--database",
        default="student_tracker.db",
        help="SQLite database file (default: student_tracker.db)",
    )
    arguments = parser.parse_args(argv)

    try:
        tracker = StudentTracker(arguments.database)
    except (OSError, sqlite3.Error) as error:
        print(f"Could not open database: {error}", file=sys.stderr)
        return 1

    print("Student Lab & Attendance Tracker")
    try:
        while True:
            print(
                "\n1. Add student\n"
                "2. Mark daily attendance\n"
                "3. Enter lab component marks\n"
                "4. Calculate attendance percentage\n"
                "5. Export student summary to CSV\n"
                "6. List students\n"
                "0. Exit"
            )
            try:
                choice = _read_nonempty("Choose an option: ")
                if choice == "0":
                    return 0
                if choice == "1":
                    usn = _read_nonempty("USN: ")
                    name = _read_nonempty("Name: ")
                    semester = _read_semester()
                    tracker.add_student(usn, name, semester)
                    print(f"Added student {usn.strip().upper()}.")
                elif choice == "2":
                    usn = _read_nonempty("USN: ")
                    attendance_date = _read_nonempty("Date (YYYY-MM-DD): ")
                    status = _read_nonempty("Status (Present/Absent): ")
                    tracker.mark_attendance(usn, attendance_date, status)
                    print("Attendance saved.")
                elif choice == "3":
                    usn = _read_nonempty("USN: ")
                    attendance_date = _read_nonempty("Date (YYYY-MM-DD): ")
                    marks = _read_marks()
                    tracker.enter_lab_marks(usn, attendance_date, marks)
                    print("Lab marks saved.")
                elif choice == "4":
                    usn = _read_nonempty("USN: ")
                    print(f"Attendance: {tracker.calculate_percentage(usn):.2f}%")
                elif choice == "5":
                    csv_path = _read_nonempty("CSV output path: ")
                    count = tracker.export_report(csv_path)
                    print(f"Exported {count} student(s) to {csv_path}.")
                elif choice == "6":
                    students = tracker.list_students()
                    if not students:
                        print("No students have been added.")
                    else:
                        for student in students:
                            print(
                                f"{student['USN']}: {student['name']} "
                                f"(semester {student['semester']})"
                            )
                else:
                    print("Choose one of the listed menu options.")
            except EOFError:
                print("\nInput closed. Exiting.")
                return 0
            except (ValueError, LookupError, OSError, sqlite3.Error) as error:
                print(f"Error: {error}")
    finally:
        tracker.close()


if __name__ == "__main__":
    raise SystemExit(main())
