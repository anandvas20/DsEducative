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