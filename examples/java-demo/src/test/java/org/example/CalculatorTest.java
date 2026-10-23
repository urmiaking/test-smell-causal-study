package org.example;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
public class CalculatorTest {
    @Test
    public void adds() {
        Calculator calc = new Calculator();
        assertEquals(4, calc.add(2, 2));
    }
}
