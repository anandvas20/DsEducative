package com.example.educationplatform;

import jakarta.persistence.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;

import java.time.*;
import java.util.*;

/*
====================================================================
 PROBLEM STATEMENT – EDUCATION PLATFORM IMPLEMENTATION
====================================================================

You are building a Course Management System for an online platform.

The platform allows:
- Students to enroll in multiple courses
- Courses to have multiple students
- Tracking of course schedules with day and time information
- Automatic enrollment date tracking
- Querying active students based on course enrollment count

You are provided with incomplete models and a repository.
You must implement them based on the following constraints:

1️⃣ Entity Relationships (@ManyToMany)
   - Implement a bidirectional Many-to-Many relationship
     between Student and Course
   - Use join table named "student_course"
   - Ensure both sides are properly maintained

2️⃣ Embeddable Entity (@Embeddable)
   - Create CourseSchedule with:
        - day (DayOfWeek)
        - startTime (LocalTime)
        - endTime (LocalTime)
   - Embed into Course entity
   - Rename day column to "day_of_week" in database

3️⃣ Custom Repository Method
   - Find active students enrolled in at least N courses
   - Only return students where isActive = true
   - Use JPQL with @Query annotation
   - Use GROUP BY + HAVING

4️⃣ Lifecycle Callback (@PrePersist)
   - Automatically set enrollmentDate when Student is created

====================================================================
*/

public class EducationPlatformApplication {
    // This class intentionally left empty.
    // In real Spring Boot app this would be @SpringBootApplication
}

/* ============================================================
   STUDENT ENTITY
   ============================================================ */

@Entity
@Table(name = "students")
class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private boolean isActive = true;

    private LocalDate enrollmentDate;

    @ManyToMany(cascade = {CascadeType.PERSIST, CascadeType.MERGE})
    @JoinTable(
            name = "student_course",
            joinColumns = @JoinColumn(name = "student_id"),
            inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    public Student() {}

    public Student(String name, boolean isActive) {
        this.name = name;
        this.isActive = isActive;
    }

    @PrePersist
    public void prePersist() {
        this.enrollmentDate = LocalDate.now();
    }

    // Helper method to maintain bidirectional consistency
    public void enrollCourse(Course course) {
        this.courses.add(course);
        course.getStudents().add(this);
    }

    // Getters

    public Long getId() { return id; }
    public String getName() { return name; }
    public boolean isActive() { return isActive; }
    public LocalDate getEnrollmentDate() { return enrollmentDate; }
    public Set<Course> getCourses() { return courses; }
}

/* ============================================================
   COURSE ENTITY
   ============================================================ */

@Entity
@Table(name = "courses")
class Course {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    @Embedded
    private CourseSchedule schedule;

    public Course() {}

    public Course(String title, CourseSchedule schedule) {
        this.title = title;
        this.schedule = schedule;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Set<Student> getStudents() { return students; }
    public CourseSchedule getSchedule() { return schedule; }
}

/* ============================================================
   EMBEDDABLE COURSE SCHEDULE
   ============================================================ */

@Embeddable
class CourseSchedule {

    @Enumerated(EnumType.STRING)
    @Column(name = "day_of_week")  // Avoid H2 reserved keyword
    private DayOfWeek day;

    private LocalTime startTime;
    private LocalTime endTime;

    public CourseSchedule() {}

    public CourseSchedule(DayOfWeek day,
                          LocalTime startTime,
                          LocalTime endTime) {
        this.day = day;
        this.startTime = startTime;
        this.endTime = endTime;
    }

    public DayOfWeek getDay() { return day; }
    public LocalTime getStartTime() { return startTime; }
    public LocalTime getEndTime() { return endTime; }
}

/* ============================================================
   REPOSITORY
   ============================================================ */

@Repository
interface StudentRepository extends JpaRepository<Student, Long> {

    @Query("""
           SELECT s FROM Student s
           JOIN s.courses c
           WHERE s.isActive = true
           GROUP BY s
           HAVING COUNT(c) >= :minCourses
           """)
    List<Student> findActiveStudentsWithMinCourses(@Param("minCourses") long minCourses);
}

/* ============================================================
   SERVICE LAYER (Optional)
   ============================================================ */

@Service
class StudentService {

    private final StudentRepository repository;

    public StudentService(StudentRepository repository) {
        this.repository = repository;
    }

    public List<Student> getActiveStudents(int minCourses) {
        return repository.findActiveStudentsWithMinCourses(minCourses);
    }
}
