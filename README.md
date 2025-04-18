import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Date;

public class DateFormatUtils {

    public static String convertToMMDDYYYY(String inputDate) {
        // Possible input date formats
        String[] inputFormats = new String[]{
            "dd-MMM-yy hh.mm.ss.SSSSSSS a",
            "yyyy-MM-dd HH:mm:ss.S",
            "yyyy-MM-dd'T'HH:mm:ss.SSSSSSS",
            "yyyy-MM-dd'T'HH:mm:ss.S",
            "yyyy-MM-dd'T'HH:mm:ss",
            "yyyy-MM-dd'T'HH:mm:ss'Z'"
        };

        SimpleDateFormat outputFormat = new SimpleDateFormat("MM/dd/yyyy");

        for (String format : inputFormats) {
            try {
                SimpleDateFormat inputFormat = new SimpleDateFormat(format);
                inputFormat.setLenient(false);
                Date date = inputFormat.parse(inputDate);
                return outputFormat.format(date);
            } catch (ParseException e) {
                // Try the next format
            }
        }

        // If none of the formats matched
        return "Invalid date";
    }
}


import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.*;

public class DateFormatUtils {

    public static String convertToMMDDYYYY(String inputDate) {
        // Output format
        DateTimeFormatter outputFormatter = DateTimeFormatter.ofPattern("MM/dd/yyyy");

        // List of possible input formatters
        List<DateTimeFormatter> inputFormatters = Arrays.asList(
            DateTimeFormatter.ofPattern("dd-MMM-yy hh.mm.ss.SSSSSSS a", Locale.ENGLISH),
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.S"),
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSSS"),
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSS"),
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS"),
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss"),
            DateTimeFormatter.ISO_OFFSET_DATE_TIME,
            DateTimeFormatter.ISO_INSTANT
        );

        for (DateTimeFormatter formatter : inputFormatters) {
            try {
                TemporalAccessor parsed = formatter.parse(inputDate);
                LocalDate date = LocalDate.from(parsed);
                return outputFormatter.format(date);
            } catch (DateTimeParseException e) {
                // Continue trying next format
            }
        }

        return "Invalid date";
    }
}
