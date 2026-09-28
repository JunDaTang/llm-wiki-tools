#### Sciences and Engineering

##### 9.2.3.1 Formulation of the Problem and the Boundary Conditions

1. Problem Formulation

The modeling and the mathematical treatment of diferent physical phenomena in classical theoretical physics, especially in modeling media considered structureless or continuously changing, such as gases, fluids, solids, the fields of classical physics, leads to the introduction of partial diferential equations. Examples are the wave (see 9.2.3.2, p. 590) and the heat equations (see 9.2.3.3, p. 591). Many problems in non-classical theoretical physics are also governed by partial diferential equations. An important area is quantum mechanics, which is based on the recognition that media and fields are discontinuous. The most famous relation is the Schroedinger equation. Linear second-order partial diferential equations occur most frequently and they have special importance in today’s natural sciences.

2. Initial and Boundary Conditions

The solution of the problems of physics, engineering, and the natural sciences must usually fulfill two basic requirements:

1. The solution must satisfy not only the diferential equation, but also certain initial and/or boundary conditions. There are problems with only initial condition or only with boundary conditions or with both. All the conditions together must determine the unique solution of the diferential equation.

2. The solution must be stable with respect to small changes in the initial and boundary conditions, i.e., its change should be arbitrarily small if the perturbations of these conditions are small enough. Then a correct problem formulation is given.

One can assume that the mathematical model of the given problem to describe the real situation is adequate only in cases when these conditions are fulfilled.

For instance, the Cauchy problem (see 9.2.1.1, 5., p. 572) is correctly defined with a diferential equation of hyperbolic type for investigating vibration processes in continuous media. This means that the values of the required function, and the values of its derivatives in a non-tangential (mostly in a normal) direction are given on an initial manifold, i.e., on a curve or on a surface.

In the case of diferential equations of elliptic type, which occur in investigations of steady state and equilibrium problems in continuous media, the formulation of the boundary value problem is correct. If the considered domain is unbounded, then the unknown function must satisfy certain given properties with unlimited increase of the independent variables.

3. Inhomogeneous Conditions and Inhomogeneous Diferential Equations

The solution of homogeneous or inhomogeneous linear partial diferential equations with inhomogeneous initial or boundary conditions can be reduced to the solution of an equation which difers from the original one only by a free term not containing the unknown function, and which has homogeneous conditions. It is suficient to replace the original function by its diference from an arbitrary twice differentiable function satisfying the given inhomogeneous conditions.

In general, one uses the fact that the solution of a linear inhomogeneous partial diferential equation with given inhomogeneous initial or boundary conditions is the sum of the solutions of the same differential equation with zero conditions and the solution of the corresponding homogeneous diferential equation with the given conditions.

To reduce the solution of the linear inhomogeneous partial diferential equation

$$
\frac { \partial ^ { 2 } u } { \partial t ^ { 2 } } - L [ u ] = g ( x , t )\tag{9.103a}
$$

with homogeneous initial conditions

$$
u \bigg | _ { t = 0 } = 0 , \quad \frac { \partial u } { \partial t } \bigg | _ { t = 0 } = 0\tag{9.103b}
$$

to the solution of the Cauchy problem for the corresponding homogeneous diferential equation, one substitutes

$$
u = \intop _ { 0 } ^ { t } \varphi ( x , t ; \tau ) d \tau .\tag{9.103c}
$$

Here $\varphi ( x , t ; \tau )$ is the solution of the diferential equation

$$
\frac { \partial ^ { 2 } u } { \partial t ^ { 2 } } - L [ u ] = 0 ,\tag{9.103d}
$$

which satisfies the boundary conditions

$$
u \Big | _ { t = \tau } = 0 , \quad \frac { \partial u } { \partial t } \Big | _ { t = \tau } = g ( x , \tau ) .\tag{9.103e}
$$

In this equation, x represents symbolically all the n variables $x _ { 1 } , x _ { 2 } , \ldots , x _ { n }$ of the n-dimensional problem. $L [ u ]$ denotes a linear diferential expression, which may contain the derivative $\frac { \partial u } { \partial t }$ , but not higherorder derivatives with respect to t.

##### 9.2.3.2 Wave Equation

The extension of oscillations in a homogeneous media is described by the wave equation

$$
\frac { \partial ^ { 2 } u } { \partial t ^ { 2 } } - a ^ { 2 } \Delta u = Q ( { \boldsymbol { x } } , t ) ,\tag{9.104a}
$$

whose right-hand side $Q ( x , t )$ vanishes when there is no perturbation. The symbol x represents the n variables $x _ { 1 } , \ldots , x _ { n }$ of the n-dimensional problem. The Laplace operator $\Delta$ (see also 13.2.6.5, 716,) is defined in the following way:

$$
\Delta u = \frac { \partial ^ { 2 } u } { { \partial { x _ { 1 } } ^ { 2 } } } + \frac { \partial ^ { 2 } u } { { \partial { x _ { 2 } } ^ { 2 } } } + \cdot \cdot \cdot + \frac { { \partial ^ { 2 } } u } { { \partial { x _ { n } } ^ { 2 } } } .\tag{9.104b}
$$

The solution of the wave equation is the wave function u. The diferential equation (9.104a) is of hyperbolic type.

1. Homogeneous Problem

The solution of the homogeneous problem with $Q ( x , t ) = 0$ and with the initial conditions

$$
u \bigg | _ { t = 0 } = \varphi ( x ) , \quad \frac { \partial u } { \partial t } \bigg | _ { t = 0 } = \psi ( x )\tag{9.105}
$$

is given for the cases $n = 1 , 2 , 3$ by the following integrals.

Case ${ \boldsymbol { n } } = 3$ (Kirchhof Formula):

$$
u ( x _ { 1 } , x _ { 2 } , x _ { 3 } , t ) = \frac { 1 } { 4 \pi a ^ { 2 } } \left[ \int \intop _ { \left( S _ { \mathrm { a t } } \right) } \frac { \psi ( \alpha _ { 1 } , \alpha _ { 2 } , \alpha _ { 3 } ) } { t } d \sigma + \frac { \partial } { \partial t } \int \intop _ { \left( S _ { \mathrm { a t } } \right) } \frac { \varphi ( \alpha _ { 1 } , \alpha _ { 2 } , \alpha _ { 3 } ) } { t } d \sigma \right] ,\tag{9.106a}
$$

where the integration is performed over the spherical surface $S _ { a t }$ given by the equation $( \alpha _ { 1 } - x _ { 1 } ) ^ { 2 } +$ $( \alpha _ { 2 } - x _ { 2 } ) ^ { 2 } + ( \stackrel { \smile } { \alpha } _ { 3 } - x _ { 3 } ) ^ { 2 } \stackrel { \cdot } { = } a ^ { 2 } t ^ { 2 }$

Case ${ \boldsymbol { n } } = 2$ (Poisson Formula):

$$
\begin{array} { r } { u ( x _ { 1 } , x _ { 2 } , t ) = \displaystyle \frac { 1 } { 2 \pi a } \Big [ \int _ { ( { \cal C } _ { \mathrm { a t } } ) } \frac { \psi ( \alpha _ { 1 } , \alpha _ { 2 } ) d \alpha _ { 1 } d \alpha _ { 2 } } { \sqrt { a ^ { 2 } t ^ { 2 } - ( \alpha _ { 1 } - x _ { 1 } ) ^ { 2 } - ( \alpha _ { 2 } - x _ { 2 } ) ^ { 2 } } } } \\ { + \frac { \partial } { \partial t } \displaystyle \iint _ { ( { \cal C } _ { \mathrm { a t } } ) } \frac { \varphi ( \alpha _ { 1 } , \alpha _ { 2 } ) d \alpha _ { 1 } d \alpha _ { 2 } } { \sqrt { a ^ { 2 } t ^ { 2 } - ( \alpha _ { 1 } - x _ { 1 } ) ^ { 2 } - ( \alpha _ { 2 } - x _ { 2 } ) ^ { 2 } } } \Big ] , } \end{array}\tag{9.106b}
$$

where the integration is performed along the circle $C _ { \mathrm { a t } }$ given by the equation $( \alpha _ { 1 } - x _ { 1 } ) ^ { 2 } + ( \alpha _ { 2 } - x _ { 2 } ) ^ { 2 } \leq$ $a ^ { 2 } t ^ { 2 }$

Case ${ n = 1 }$ (d’Alembert formula):

$$
u ( x _ { 1 } , t ) = { \frac { \varphi ( x _ { 1 } + a t ) + \varphi ( x _ { 1 } - a t ) } { 2 } } + { \frac { 1 } { 2 a } } \int _ { x _ { 1 } - a t } ^ { x _ { 1 } + a t } \psi ( \alpha ) d \alpha .\tag{9.106c}
$$

2. Inhomogeneous Problem

In the case, when $Q ( x , t ) \neq 0$ , one has to add to the right-hand sides of $\left( 9 . 1 0 6 \mathrm { a } , \mathrm { b } , \mathrm { c } \right)$ the correcting terms:

Case ${ \boldsymbol { n } } = 3$ (Retarded Potential): For a domain K given by $r \leq a t $ with

$$
r = { \sqrt { ( \xi _ { 1 } - x _ { 1 } ) ^ { 2 } + ( \xi _ { 2 } - x _ { 2 } ) ^ { 2 } + ( \xi _ { 3 } - x _ { 3 } ) ^ { 2 } } } , { \mathrm { t h e ~ c o r r e c t i o n ~ t e r m ~ i s } }
$$

$$
{ \frac { 1 } { 4 \pi a ^ { 2 } } } \iiint { \frac { Q \left( \xi _ { 1 } , \xi _ { 2 } , \xi _ { 3 } , t - { \frac { r } { a } } \right) } { r } } d \xi _ { 1 } d \xi _ { 2 } d \xi _ { 3 } .\tag{9.107a}
$$

$$
\mathrm { C a s e } n = 2 : \ \begin{array} { c } { { \displaystyle \frac { 1 } { 2 \pi a } \iiint \int \frac { Q ( \xi _ { 1 } , \xi _ { 2 } , \tau ) d \xi _ { 1 } d \xi _ { 2 } d \tau } { ( K ) ^ { 2 } ( t - \tau ) ^ { 2 } - ( \xi _ { 1 } - x _ { 1 } ) ^ { 2 } - ( \xi _ { 2 } - x _ { 2 } ) ^ { 2 } } , } } \end{array}\tag{9.107b}
$$

where K is a domain o $\xi _ { 1 } , \xi _ { 2 } , \tau$ space defined by the inequalities $0 \leq \tau \leq t , ( \xi _ { 1 } - x _ { 1 } ) ^ { 2 } + ( \xi _ { 2 } - x _ { 2 } ) ^ { 2 } \leq$ $a ^ { 2 } ( t - \tau ) ^ { 2 }$

$$
\displaystyle \mathrm { C a s e } n = { \bf 1 : } \quad \frac { 1 } { 2 a } \int \int Q ( \xi , \tau ) d \xi d \tau ,\tag{9.107c}
$$

where T is the triangle $0 \leq \tau \leq t , | \xi - x _ { 1 } | \leq a | t - \tau |$ . a denotes the wave velocity of the perturbation.

##### 9.2.3.3 Heat Conduction and Diffusion Equation for Homogeneous Media

1. Three-Dimensional Heat Conduction Equation

The propagation of heat in a homogeneous medium is described by a linear second-order partial diferential equation of parabolic type

$$
\frac { \partial u } { \partial t } - a ^ { 2 } \Delta u = Q ( x , t ) ,\tag{9.108a}
$$

where $\Delta$ is the three-dimensional Laplace operator defined in three directions of propagation $x _ { 1 } , x _ { 2 }$ $x _ { 3 } ,$ , determined by the position vector r. If the heat flow has neither source nor sink, the right-hand side vanishes since $Q ( x , t ) \bar { = } 0$

The Cauchy problem can be posed in the following way: It is to determine a bounded solution $\boldsymbol { u } ( \boldsymbol { x } , t )$ for

$t > 0$ , where $u | _ { t = 0 } = f ( x )$ . The requirement of boundedness guarantees the uniqueness of the solution. For the homogeneous diferential equation with $Q ( x , t ) = 0$ , one gets the wave function

$$
\begin{array} { l } { { \displaystyle { u ( x _ { 1 } , x _ { 2 } , x _ { 3 } , t ) = \frac { 1 } { ( 2 a \sqrt { \pi t } ) ^ { n } } \int \int \int \int \int f \left( \alpha _ { 1 } , \alpha _ { 2 } , \alpha _ { 3 } \right) } } } \\ { { \displaystyle { \phantom { \frac { 1 } { ( 2 a \sqrt { \pi t } ) ^ { n } } } - \infty - \infty } } } \\ { { \displaystyle { \phantom { \frac { 1 } { ( 2 a \sqrt { \pi t } ) ^ { n } } } \cdot \exp \left( - \frac { ( x _ { 1 } - \alpha _ { 1 } ) ^ { 2 } + ( x _ { 2 } - \alpha _ { 2 } ) ^ { 2 } + ( x _ { 3 } - \alpha _ { 3 } ) ^ { 2 } } { 4 a ^ { 2 } t } \right) d \alpha _ { 1 } d \alpha _ { 2 } d \alpha _ { 3 } } . } } \end{array}\tag{9.108b}
$$

In the case of an inhomogeneous diferential equation with $Q ( x , t ) \neq 0$ , one has to add to the right-hand side of (9.108b) the following expression:

$$
\begin{array} { r l }   { \int _ { 0 } ^ { t } [ \begin{array} { l } { \int _ { - \infty } \int \displaylimits _ { - \infty } ^ { + \infty } \int \displaylimits _ { - \infty } ^ { + \infty } \frac { Q ( \alpha _ { 1 } , \alpha _ { 2 } , \alpha _ { 3 } ) } { [ 2 a \sqrt { \pi ( t - \tau ) } ] ^ { n } } } \\ { \cdot \exp ( - \frac { ( x _ { 1 } - \alpha _ { 1 } ) ^ { 2 } + ( x _ { 2 } - \alpha _ { 2 } ) ^ { 2 } + ( x _ { 3 } - \alpha _ { 3 } ) ^ { 2 } } { 4 a ^ { 2 } ( t - \tau ) } ) d \alpha _ { 1 } d \alpha _ { 2 } d \alpha _ { 3 } ] d \tau . } } \end{array} \end{array}\tag{9.108c}
$$

The problem of determining $\boldsymbol { u } ( \boldsymbol { x } , t )$ for $t < 0$ , if the values $u ( x , 0 )$ are given, cannot be solved in this way, since the Cauchy problem is not correctly formulated in this case.

Since the temperature diference is proportional to the heat, one often introduces $u = T ( \vec { \bf r } , t )$ (temperature field) and $a ^ { 2 } = D _ { W }$ (heat difusion constant or thermal conductivity) to get

$$
\frac { \partial T } { \partial t } - D _ { W } \Delta T = Q _ { W } ( \vec { \bf r } , t ) .\tag{9.108d}
$$

2. Three-Dimensional Difusion Equation

In analogy to the heat equation, the propagation of a concentration $C$ in a homogeneous medium is described by the same linear partial diferential equation (9.108a) and (9.108d), where $D _ { W }$ is replaced by the three-dimensional difusion coeficient $D _ { C }$ . The difusion equation is:

$$
\frac { \partial C } { \partial t } - D _ { C } \Delta C = Q _ { C } ( \vec { \bf r } , t ) .\tag{9.109}
$$

One gets the solutions by changing the symbols in the wave equations (9.108b) and (9.108c).

##### 9.2.3.4 Potential Equation

The linear second-order partial diferential equation

$$
\Delta u = - 4 \pi \varrho\tag{9.110a}
$$

is called the potential equation or Poisson diferential equation (see 13.5.2, p. 729), which makes the determination of the potential $u ( x )$ of a scalar field determined by a scalar point function $\varrho ( x )$ possible, where x has the coordinates $x _ { 1 } , x _ { 2 } , x _ { 3 }$ and $\Delta$ is the Laplace operator. The solution, the potential $u _ { M } ( x _ { 1 } , x _ { 2 } , x _ { 3 } )$ at the point $M$ , is discussed in 13.5.2, p. 729.

One gets the Laplace diferential equation (see 13.5.1, p. 729) for the homogeneous diferential equation with $\varrho \equiv 0$

$$
\Delta u = 0 .\tag{9.110b}
$$

The diferential equations (9.110a) and (9.110b) are of elliptic type.
