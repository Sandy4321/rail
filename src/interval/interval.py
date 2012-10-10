'''
interval.py

Classes for storing and operating on intervals.
'''

## {{{ http://code.activestate.com/recipes/576816/ (r1)
class Interval(object):
    
    """
    Represents an interval. 
    Defined as half-open interval [start,end), which includes the start position but not the end.
    Start and end do not have to be numeric types. 
    """
    
    def __init__(self, start, end):
        "Construct, start must be <= end."
        if start > end:
            raise ValueError('Start (%s) must not be greater than end (%s)' % (start, end))
        self._start = start
        self._end = end
        
         
    start = property(fget=lambda self: self._start, doc="The interval's start")
    end = property(fget=lambda self: self._end, doc="The interval's end")
     

    def __str__(self):
        "As string."
        return '[%s,%s)' % (self.start, self.end)
    
    
    def __repr__(self):
        "String representation."
        return '[%s,%s)' % (self.start, self.end)
    
    
    def __cmp__(self, other):
        "Compare."
        if None == other:
            return 1
        start_cmp = cmp(self.start, other.start)
        if 0 != start_cmp:
            return start_cmp
        else:
            return cmp(self.end, other.end)


    def __hash__(self):
        "Hash."
        return hash(self.start) ^ hash(self.end)
    
    
    def intersection(self, other):
        "Intersection. @return: An empty intersection if there is none."
        if self > other:
            other, self = self, other
        if self.end <= other.start:
            return Interval(self.start, self.start)
        return Interval(other.start, self.end)


    def hull(self, other):
        "@return: Interval containing both self and other."
        return Interval(min(self.start, other.start), max(self.end, other.end))

    def overlap(self, other):
        "@return: True iff self intersects other."
        if self > other:
            other, self = self, other
        return self.end > other.start

    def overlap_or_adjacent(self, other):
        "@return: True iff self intersects other."
        if self > other:
            other, self = self, other
        return self.end >= other.start
         

    def __contains__(self, item):
        "@return: True iff item in self."
        return self.start <= item and item < self.end
         

    def zero_in(self):
        "@return: True iff 0 in self."
        return self.start <= 0 and 0 < self.end
         

    def subset(self, other):
        "@return: True iff self is subset of other."
        return self.start >= other.start and self.end <= other.end
         

    def proper_subset(self, other):
        "@return: True iff self is proper subset of other."
        return self.start > other.start and self.end < other.end
         

    def empty(self):
        "@return: True iff self is empty."
        return self.start == self.end
         

    def singleton(self):
        "@return: True iff self.end - self.start == 1."
        return self.end - self.start == 1
    
    
    def separation(self, other):
        "@return: The distance between self and other."
        if self > other:
            other, self = self, other
        if self.end > other.start:
            return 0
        else:
            return other.start - self.end
## end of http://code.activestate.com/recipes/576816/ }}}

class FlatIntervals(object):

    '''
    Holds a set of intervals.  When a new interval is added, it is
    merged with any intervals it overlaps.
    '''
    
    def __init__(self):
        self._ivals = []

    def __len__(self):
        return len(self._ivals)
    
    def add(self, ival):
        todel = []
        for i in xrange(0, len(self._ivals)):
            oival = self._ivals[i]
            if ival.overlap_or_adjacent(oival):
                ival = ival.hull(oival)
                todel.append(i)
        for i in todel[::-1]:
            self._ivals.pop(i)
        self._ivals.append(ival)
    
    def coverage(self):
        tot = 0
        for i in self._ivals:
            tot += (i.end - i.start)
        return tot
    
    def __iter__(self):
        return iter(self._ivals)

if __name__ == '__main__':
    import unittest

    class TestFlatIntervals(unittest.TestCase):

        def test1(self):
            iv = FlatIntervals()
            iv.add(Interval(10, 100))
            self.assertEquals(1, len(iv))
            self.assertEquals(90, iv.coverage())
            iv.add(Interval(200, 300))
            self.assertEquals(2, len(iv))
            self.assertEquals(190, iv.coverage())

        def test2(self):
            iv = FlatIntervals()
            iv.add(Interval(10, 100))
            self.assertEquals(1, len(iv))
            self.assertEquals(90, iv.coverage())
            iv.add(Interval(-10, 10))
            self.assertEquals(1, len(iv))
            self.assertEquals(110, iv.coverage())

        def test3(self):
            iv = FlatIntervals()
            iv.add(Interval(10, 100))
            self.assertEquals(1, len(iv))
            self.assertEquals(90, iv.coverage())
            iv.add(Interval(50, 60))
            self.assertEquals(1, len(iv))
            self.assertEquals(90, iv.coverage())

        def test4(self):
            iv = FlatIntervals()
            iv.add(Interval(10, 100))
            self.assertEquals(1, len(iv))
            self.assertEquals(90, iv.coverage())
            iv.add(Interval(50, 110))
            self.assertEquals(1, len(iv))
            self.assertEquals(100, iv.coverage())

    unittest.main()
